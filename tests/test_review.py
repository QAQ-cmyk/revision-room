"""Boundary and failure-path tests. Real game/Codex integration is checked separately."""
import copy
from http.client import HTTPConnection
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import server


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.worker = engine.ReviewEngine(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def job(self, status="complete"):
        value = {"id":"test-run", "name":"测试", "status":status, "stage":"测试", "createdAt":engine.now(),
                 "buildName":"Test", "summary":"测试摘要", "checks":[], "screenshots":[], "findings":[], "events":[], "coverage":[], "visual":None}
        self.worker.jobs[value["id"]] = value
        self.worker.save(value["id"])
        return value

    def test_report_cannot_pass_without_checks_or_with_errors(self):
        for value in [{"passed":True,"checks":[],"errors":[]},{"passed":True,"checks":["ok"],"errors":["bad"]},{"passed":"true","checks":["ok"],"errors":[]}]:
            with self.assertRaises(ValueError): engine.check_report(value)
        self.assertFalse(engine.check_report({"passed":False,"checks":[],"errors":[]})["passed"])

    def test_visual_must_reference_supplied_screenshot(self):
        value = {"summary":"测试总结", "strengths":[], "limitations":[], "inspected_screenshots":["a"], "findings":[{
            "title":"标题", "observation":"现象", "impact":"影响", "recommendation":"建议", "verify":"复测", "severity":"medium", "confidence":"high", "screenshot_id":"a", "region":{"x":0,"y":0,"w":100,"h":100}}]}
        self.assertEqual(engine.validate_review(value, {"a"}),value)
        for change in [ {"screenshot_id":"invented"}, {"region":{"x":90,"y":0,"w":11,"h":20}}, {"region":{"x":0,"y":0,"w":float('nan'),"h":20}}, {"region":{"x":0,"y":0,"w":True,"h":20}}, {"verify":""} ]:
            wrong=copy.deepcopy(value); wrong["findings"][0].update(change)
            with self.assertRaises(ValueError): engine.validate_review(wrong, {"a"})

    def test_restarting_does_not_turn_unfinished_run_into_success(self):
        self.job("running")
        restarted=engine.ReviewEngine(self.root)
        self.assertEqual(restarted.get("test-run")["status"],"interrupted")
        self.assertIsNone(restarted.active)

    def test_cancel_preserves_valid_images_and_ignores_partial_capture(self):
        self.job("running")
        folder=self.root / "test-run" / "opening"; folder.mkdir()
        (folder / "broken.png").write_bytes(b"partial")
        (folder / "valid.png").write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",1280,720)+b"\x00\x00\x00\x00IEND\xaeB\x60\x82")
        self.worker.active="test-run"
        with patch.object(engine,"fingerprint",return_value={}), patch.object(self.worker,"_run_test",side_effect=engine.Cancelled()):
            self.worker._run("test-run",self.root / "StarTide.exe",True)
        result=self.worker.get("test-run")
        self.assertEqual(result["status"],"cancelled")
        self.assertEqual(len(result["screenshots"]),1)
        self.assertIsNone(self.worker.active)

    def test_codex_failure_keeps_test_evidence_and_is_partial(self):
        self.job("running")
        self.worker.active="test-run"
        with patch.object(engine,"fingerprint",return_value={}), patch.object(self.worker,"_run_test"), patch.object(self.worker,"_collect",return_value=[]), patch.object(self.worker,"_visual",side_effect=ValueError("network unavailable")):
            self.worker._run("test-run",self.root / "StarTide.exe",True)
        result=self.worker.get("test-run")
        self.assertEqual(result["status"],"partial")
        self.assertEqual(result["visualError"],"network unavailable")
        self.assertIsNone(self.worker.active)

    def test_game_change_invalidates_run(self):
        self.job("running")
        with patch.object(engine,"fingerprint",side_effect=[{"id":"before"},{"id":"after"}]), patch.object(self.worker,"_run_test"), patch.object(self.worker,"_collect",return_value=[]):
            self.worker._run("test-run",self.root / "StarTide.exe",True)
        self.assertEqual(self.worker.get("test-run")["status"],"error")

    def test_finding_status_persists_but_cannot_claim_automatic_fix(self):
        value=self.job();value["findings"]=[{"id":"one","state":"open"}]
        self.worker.set_finding_state("test-run","one","retest")
        self.assertEqual(engine.ReviewEngine(self.root).get("test-run")["findings"][0]["state"],"retest")
        with self.assertRaises(ValueError):self.worker.set_finding_state("test-run","one","fixed")

    def test_only_supported_project_builds_may_execute(self):
        with self.assertRaises(ValueError):engine.validate_game(str(self.root / "StarTide.exe"))
        project=self.root / "project"; build=project / "Build";build.mkdir(parents=True)
        (build/"StarTide.exe").write_bytes(b"fake exe")
        with patch.object(engine,"GAME_ROOT",project):
            with self.assertRaises(ValueError):engine.validate_game(str(build))
            managed=build / "StarTide_Data" / "Managed";managed.mkdir(parents=True)
            (managed/"Assembly-CSharp.dll").write_bytes(b"OpeningExperienceChecks ChapterRuntimeChecks")
            (build/"UnityPlayer.dll").write_bytes(b"fixture")
            self.assertEqual(engine.validate_game(str(build)),build/"StarTide.exe")
            initial=engine.fingerprint(build/"StarTide.exe")
            (build/"StarTide_Data"/"resources.assets").write_bytes(b"new art")
            self.assertNotEqual(initial,engine.fingerprint(build/"StarTide.exe"))

    def test_http_origin_path_and_data_boundaries(self):
        self.job()
        folder=self.root/"test-run"; (folder/"saves").mkdir()
        (folder/"saves"/"save.json").write_text('{}')
        (folder/"proof.json").write_text('{}')
        with patch.object(server,"ENGINE",self.worker),patch.object(server,"RUNS",self.root):
            for bad in ["../outside.json","../../server.py","saves/save.json"]:
                with self.assertRaises(ValueError):server.permitted_asset("test-run",bad)
            self.assertEqual(server.permitted_asset("test-run","proof.json"),folder/"proof.json")
            httpd=server.ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
            thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
            try:
                def request(method,path,body=None,headers=None):
                    conn=HTTPConnection("127.0.0.1",httpd.server_port,timeout=3)
                    conn.request(method,path,body=body,headers=headers or {})
                    result=conn.getresponse(); data=result.read();code=result.status;conn.close();return code,data
                self.assertEqual(request("GET","/api/health")[0],200)
                self.assertEqual(request("GET","/api/health",headers={"Host":"evil.example"})[0],403)
                self.assertEqual(request("POST","/api/start",'{}',{"Content-Type":"application/json"})[0],403)
                headers={"Content-Type":"application/json","X-Revision-Token":server.TOKEN,"Origin":"https://evil.example"}
                self.assertEqual(request("POST","/api/start",'{}',headers)[0],403)
                headers.pop("Origin")
                self.assertEqual(request("POST","/api/start",'[]',headers)[0],400)
                self.assertEqual(request("GET","/evidence/test-run/../outside.json")[0],404)
                self.assertEqual(request("GET","/evidence/test-run/saves/save.json")[0],404)
                self.assertEqual(request("GET","/api/runs/test-run/markdown")[0],200)
                self.assertEqual(request("GET",quote("/original/修订室_Grok原版.html"))[0],404)
            finally:
                httpd.shutdown();httpd.server_close();thread.join(3)


if __name__=="__main__":unittest.main(verbosity=2)
