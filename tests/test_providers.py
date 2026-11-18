"""Real local HTTP round trips; no provider credentials or paid API calls."""
import base64
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import providers
import server

REVIEW = {"summary":"本地模拟评审", "strengths":[], "limitations":["测试数据"], "inspected_screenshots":["opening/01_opening"], "findings":[]}
SCREENSHOT_REVIEW = {**REVIEW, "summary":"本地模拟完成（功能测试，不是 AI 判断）", "inspected_screenshots":["uploads/01"], "findings":[{
    "title":"测试用视觉建议", "observation":"本地接口模拟返回的证据描述", "impact":"用于检查完整流程", "recommendation":"核对图片与清单", "verify":"导出后应保留同一张图片",
    "severity":"medium", "confidence":"high", "screenshot_id":"uploads/01", "region":{"x":30,"y":30,"w":40,"h":35}}]}


class MockProvider(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append((self.path, dict(self.headers), body))
        if body["model"] == "slow":
            self.server.release.wait(3)
        status = 200
        if body["model"] == "unauthorized":
            status, result = 401, {"error": "echo: " + self.headers.get("Authorization", "")}
        elif body["model"] == "redirect":
            self.send_response(307); self.send_header("Location", self.server.url + "/stolen"); self.end_headers(); return
        else:
            result = REVIEW if body["model"] in ("review", "invented") else {"left":"blue", "right":"orange"}
            if body["model"] == "screenshot-review": result = SCREENSHOT_REVIEW
            if body["model"] == "invented": result = {**REVIEW, "inspected_screenshots":["invented"]}
            if body["model"] == "wrong-colors": result = {"left":"red", "right":"blue"}
            if body["model"] == "echo": result = {"summary":"credential " + self.headers.get("Authorization", "")}
            text = json.dumps(result)
            if body["model"] == "malformed": text = "not json"
            finish = "length" if body["model"] == "truncated" else "stop"
            result = {"choices":[{"message":{"content":text},"finish_reason":finish}], "usage":{"prompt_tokens":12,"completion_tokens":4}}
            if self.path.endswith("/messages"):
                result = {"content":[{"type":"text","text":text}], "stop_reason":"end_turn", "usage":{"input_tokens":12,"output_tokens":4}}
        raw = json.dumps(result).encode()
        self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(raw))); self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):pass


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = ThreadingHTTPServer(("127.0.0.1",0),MockProvider)
        cls.remote.url = f"http://127.0.0.1:{cls.remote.server_port}"
        cls.remote.calls=[]; cls.remote.release=threading.Event()
        cls.thread=threading.Thread(target=cls.remote.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.remote.release.set();cls.remote.shutdown();cls.remote.server_close();cls.thread.join()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=providers.ProfileStore(self.root / "profiles.json")
        self.profile={"id":"","name":"本地测试", "preset":"custom", "protocol":"openai", "baseUrl":self.remote.url+"/v1", "model":"colors", "maxTokens":8192,"tokenParam":"max_tokens","apiKey":"dummy-test-secret","noKey":False}
        self.remote.calls.clear()

    def tearDown(self):self.temp.cleanup()

    def test_dpapi_persistence_never_returns_secret(self):
        saved=self.store.save(self.profile);pid=saved["savedId"]
        self.assertNotIn(self.profile["apiKey"],json.dumps(saved))
        self.assertNotIn(self.profile["apiKey"],self.store.path.read_text(encoding="utf-8"))
        recovered=providers.ProfileStore(self.store.path)
        self.assertEqual(recovered.resolve(pid)["apiKey"],self.profile["apiKey"])
        kept=recovered.save({**self.profile,"id":pid,"apiKey":"","name":"renamed"})
        self.assertEqual(recovered.resolve(pid)["apiKey"],self.profile["apiKey"])
        with self.assertRaisesRegex(ValueError,"重新填写"):
            recovered.save({**self.profile,"id":pid,"apiKey":"","baseUrl":"https://example.invalid/v1"})
        recovered.delete(pid);self.assertEqual(recovered.public()["defaultId"],"codex")
        self.assertEqual(providers.ProfileStore(self.store.path).public()["profiles"],[])

    def test_invalid_endpoint_or_profile_is_rejected_before_network(self):
        for url in ["http://example.org/v1", "https://host/v1?key=secret", "https://user:pass@host/v1", "file:///tmp/x", "https://host/v1/messages", "https://{WorkspaceId}.host/v1", "https://host:bad/v1", "https://host\\evil/v1"]:
            with self.subTest(url=url),self.assertRaises(ValueError): self.store.draft({**self.profile,"baseUrl":url})
        with self.assertRaises(ValueError):self.store.draft({**self.profile,"apiKey":""})
        with self.assertRaises(ValueError):self.store.draft({**self.profile,"noKey":True,"baseUrl":"https://example.org/v1"})
        with self.assertRaises(ValueError):self.store.draft({**self.profile,"maxTokens":True})
        self.assertEqual(len(self.remote.calls),0)

    def test_failed_save_does_not_change_live_config(self):
        with patch.object(self.store,"_write",side_effect=OSError("disk full")),self.assertRaises(ValueError):self.store.save(self.profile)
        self.assertEqual(self.store.public()["profiles"],[])
        pid=self.store.save(self.profile)["savedId"]
        with patch.object(self.store,"_write",side_effect=OSError("disk full")):
            with self.assertRaises(ValueError): self.store.select("codex")
            self.assertEqual(self.store.public()["defaultId"],pid)
            with self.assertRaises(ValueError): self.store.delete(pid)
            self.assertEqual(len(self.store.public()["profiles"]),1)

    def imported_image(self):
        raw=(engine.BASE/"web"/"demo"/"hud.png").read_bytes()
        return {"name":"../../unsafe-name.png", "data":base64.b64encode(raw).decode()}

    def wait_for_job(self, worker, job):
        deadline=time.monotonic()+5
        while worker.active and time.monotonic()<deadline: time.sleep(.02)
        self.assertIsNone(worker.active)
        return worker.get(job)

    def test_imported_screenshots_complete_without_game_or_codex(self):
        worker=engine.ReviewEngine(self.root/"runs")
        with patch.object(engine,"codex_info",side_effect=AssertionError("no Codex")),patch.object(engine,"validate_game",side_effect=AssertionError("no game")):
            job=worker.start_images({"name":"My game", "context":"2D adventure", "images":[self.imported_image()]},{**self.profile,"model":"screenshot-review"})
            report=self.wait_for_job(worker,job)
        self.assertEqual(report["status"],"complete");self.assertEqual(report["checks"],[])
        self.assertEqual(report["screenshots"][0]["path"],"uploads/01.png")
        self.assertEqual(report["findings"][0]["screenshot_id"],"uploads/01")
        self.assertIn("uploads/01.png",worker.markdown(job))
        self.assertEqual(len(self.remote.calls),1)
        prompt=self.remote.calls[0][2]["messages"][0]["content"][0]["text"]
        self.assertIn("2D adventure",prompt);self.assertNotIn("星潮漂流",prompt)
        self.assertNotIn(self.profile["apiKey"],json.dumps(report))

    def test_invalid_imports_do_not_create_history_or_call_api(self):
        worker=engine.ReviewEngine(self.root/"runs")
        for images in [[],[self.imported_image()]*11,[{"name":"x","data":"!badbase64"}],[{"name":"x","data":base64.b64encode(b"not an image").decode()}]]:
            with self.subTest(count=len(images)),self.assertRaises(ValueError):worker.start_images({"name":"test","images":images},self.profile)
        self.assertEqual(worker.history(),[]);self.assertEqual(self.remote.calls,[])
        self.assertEqual(list(worker.root.iterdir()),[])

    def test_import_failure_preserves_evidence_and_reports_partial(self):
        worker=engine.ReviewEngine(self.root/"runs")
        job=worker.start_images({"name":"test","images":[self.imported_image()]},{**self.profile,"model":"unauthorized"})
        report=self.wait_for_job(worker,job)
        self.assertEqual(report["status"],"partial")
        self.assertIsNone(report["visual"]);self.assertEqual(report["findings"],[])
        self.assertTrue((worker.root/job/report["screenshots"][0]["path"]).is_file())
        self.assertNotIn(self.profile["apiKey"],report["visualError"])

    def test_both_protocols_send_a_real_png_and_correct_headers(self):
        for protocol, suffix, token in [("openai","/chat/completions","max_completion_tokens"),("anthropic","/messages","max_tokens")]:
            with self.subTest(protocol=protocol):
                self.assertTrue(providers.test_vision({**self.profile,"protocol":protocol,"tokenParam":token})["ok"])
                path,headers,payload=self.remote.calls[-1]
                self.assertTrue(path.endswith(suffix));self.assertEqual(payload[token],1024)
                content=payload["messages"][0]["content"];image=content[2]
                if protocol=="anthropic":
                    encoded=image["source"]["data"];self.assertEqual(headers["X-Api-Key"],self.profile["apiKey"])
                    self.assertEqual(headers["Anthropic-Version"],"2023-06-01")
                else:
                    encoded=image["image_url"]["url"].split(",")[1];self.assertEqual(headers["Authorization"],"Bearer "+self.profile["apiKey"])
                self.assertTrue(base64.b64decode(encoded).startswith(b"\x89PNG"))
                self.assertNotIn('"blue"', content[0]["text"])

    def test_errors_are_redacted_and_never_retried(self):
        for model in ["unauthorized","redirect","malformed","truncated","wrong-colors"]:
            self.remote.calls.clear()
            with self.subTest(model=model),self.assertRaises(ValueError) as error:providers.test_vision({**self.profile,"model":model})
            self.assertNotIn(self.profile["apiKey"],str(error.exception));self.assertEqual(len(self.remote.calls),1)
        result,_=providers.request_vision({**self.profile,"model":"echo"},"test",[("one",b"png")])
        self.assertNotIn(self.profile["apiKey"],json.dumps(result))

    def test_cancellation_returns_promptly_without_retry(self):
        stop=threading.Event();timer=threading.Timer(.2,stop.set);timer.start();start=time.monotonic()
        try:
            with self.assertRaises(providers.RequestCancelled):providers.request_vision({**self.profile,"model":"slow"},"test",[("one",b"png")],stop)
            self.assertLess(time.monotonic()-start,1);self.assertEqual(len(self.remote.calls),1)
        finally:self.remote.release.set();timer.join()

    def test_external_review_enters_report_without_codex_or_credentials(self):
        worker=engine.ReviewEngine(self.root/"runs");job="fixture";folder=worker.root/job/"opening";folder.mkdir(parents=True)
        (folder/"01_opening.png").write_bytes(b"png")
        worker.jobs[job]={"id":job,"findings":[],"checks":[],"screenshots":[],"visual":None}
        shots=[{"id":"opening/01_opening","label":"开场","path":"opening/01_opening.png","kind":"opening","width":1280,"height":720}]
        with patch.object(engine,"codex_info",side_effect=AssertionError("should not invoke Codex")):
            worker._visual(job,shots,[],{**self.profile,"model":"review"})
        result=worker.get(job);self.assertEqual(result["visual"]["summary"],REVIEW["summary"])
        self.assertEqual(result["visualProvider"],self.profile["name"])
        for file in (worker.root/job).rglob("*.json"):
            self.assertNotIn(self.profile["apiKey"],file.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):worker._visual(job,shots,[],{**self.profile,"model":"invented"})

    def test_settings_http_auth_and_metadata_boundaries(self):
        with patch.object(server,"PROFILES",self.store),patch.object(server,"INFO",{}),patch.object(server,"builds",return_value=[]):
            local=ThreadingHTTPServer(("127.0.0.1",0),server.Handler);thread=threading.Thread(target=local.serve_forever,daemon=True);thread.start()
            def call(path,body=None,authorized=True):
                conn=HTTPConnection("127.0.0.1",local.server_port,timeout=5)
                headers={"Content-Type":"application/json"}
                if authorized:headers["X-Revision-Token"]=server.TOKEN
                conn.request("POST" if body is not None else "GET",path,json.dumps(body) if body is not None else None,headers)
                response=conn.getresponse();status=response.status;data=json.load(response);conn.close();return status,data
            try:
                self.assertEqual(call("/api/profiles/save",self.profile,False)[0],403)
                status,saved=call("/api/profiles/save",self.profile);self.assertEqual(status,200)
                self.assertNotIn(self.profile["apiKey"],json.dumps(call("/api/bootstrap")[1]))
                self.assertTrue(call("/api/profiles/test",{**self.profile,"id":saved["savedId"],"apiKey":""})[1]["ok"])
            finally:local.shutdown();local.server_close();thread.join()


if __name__=="__main__":unittest.main()
