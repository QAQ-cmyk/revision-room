"""Replay a bounded keyboard route in an isolated Edge window and retain its evidence."""
import importlib.util
import threading
import uuid
from datetime import datetime
from urllib.parse import urlsplit

from engine import Cancelled, ZONE, atomic_json, now, sha256


def available():
    return importlib.util.find_spec("playwright") is not None


def game_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None or parsed.password is not None or "\\" in value
            or not parsed.port or len(value) > 2048 or any(ord(c) < 32 for c in value)):
        raise ValueError("请填写带端口的本机游戏网址，例如 http://127.0.0.1:4173/pilot/。")
    return value


def validate(body):
    url = body.get("url")
    if not isinstance(url, str):
        raise ValueError("缺少游戏网址")
    game_url(url)
    route = body.get("route")
    if not isinstance(route, dict) or set(route) != {"name", "viewport", "steps"}:
        raise ValueError("路线需要 name、viewport、steps 三项")
    name, viewport, steps = route["name"], route["viewport"], route["steps"]
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("请给路线取一个 1 至 100 字的名称")
    if (not isinstance(viewport, list) or len(viewport) != 2 or
            any(type(n) is not int or not 240 <= n <= 2560 for n in viewport)):
        raise ValueError("viewport 需要两个 240 至 2560 之间的整数")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 10:
        raise ValueError("每条路线需要 1 至 10 个步骤")
    fields = {"capture": set(), "click": {"selector"}, "key": {"key"}, "hold": {"key", "ms"},
              "visible": {"selector"}, "text": {"selector", "text"}}
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("action"), str) or step["action"] not in fields:
            raise ValueError("不支持的操作，请参考内置路线")
        if set(step) != {"label", "action"} | fields[step["action"]]:
            raise ValueError("路线步骤字段不完整或多余，请参考内置路线")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 300 for k, v in step.items() if k != "ms"):
            raise ValueError("步骤名称和参数需要填写 1 至 300 字")
        if "ms" in step and (type(step["ms"]) is not int or not 1 <= step["ms"] <= 5000):
            raise ValueError("按住时间须在 1 至 5000 毫秒之间")
    return url, route


def start(engine, body):
    url, route = validate(body)
    if not available():
        raise ValueError("网页试玩需要 Playwright。请使用 Windows 便携包，或为当前 Python 安装 requirements-web.txt。")
    with engine.lock:
        if engine.active:
            raise ValueError("已有试玩正在进行")
        job = datetime.now(ZONE).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        (engine.root / job / "web").mkdir(parents=True)
        engine.jobs[job] = dict(id=job, name=route["name"], buildName="网页试玩", mode="web", url=url, route=route,
            createdAt=now(), endedAt=None, status="running", stage="正在打开独立浏览器", step=0, events=[], checks=[],
            screenshots=[], findings=[], visual=None, visualProvider="浏览器实测", reviewerId="web", visionRequested=False,
            summary="正在执行路线", coverage=["按顺序执行已配置的操作，每一步保留可见画面与检查记录。首个失败会停止后续步骤。",
            "键盘输入与可见元素可以复测，声音、手感和路线以外的内容仍需试玩者判断。"])
        engine.active = job
        engine.stop_event.clear()
        engine.save(job)
        threading.Thread(target=run, args=(engine, job, url, route), daemon=True).start()
    return job


def perform(page, step):
    action = step["action"]
    if action == "capture":
        return "记录当前画面"
    if action == "click":
        page.locator(step["selector"]).click(timeout=6000)
        return "已点击 " + step["selector"]
    if action in {"key", "hold"}:
        page.keyboard.press(step["key"], delay=step.get("ms", 70))
        return "已输入 " + step["key"]
    node = page.locator(step["selector"])
    node.wait_for(state="visible", timeout=6000)
    if action == "text":
        from playwright.sync_api import expect
        expect(node).to_contain_text(step["text"], timeout=6000)
        return "页面文字包含 “" + step["text"] + "”"
    box = node.bounding_box()
    viewport = page.viewport_size
    if not box:
        raise ValueError("元素没有可见边界")
    x, y, w, h = (box[k] for k in ("x","y","width","height"))
    bounds = f"元素范围 ({x:.0f}, {y:.0f}) 至 ({x+w:.0f}, {y+h:.0f})，窗口 {viewport['width']} × {viewport['height']}"
    if x < -0.5 or y < -0.5 or x+w > viewport["width"]+.5 or y+h > viewport["height"]+.5:
        raise ValueError("元素没有完全落在可见区域。" + bounds)
    return bounds


def run(engine, job, url, route):
    root = engine.root / job
    shots, checks, findings = [], [], []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.launch(channel="msedge", headless=True)
            try:
                width, height = route["viewport"]
                page = browser.new_page(viewport={"width":width,"height":height}, accept_downloads=False)
                page.set_default_timeout(6000)
                response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if response is None or not response.ok:
                    raise ValueError("游戏页面没有正常返回，请确认本机游戏服务已经启动")
                game_url(page.url)
                for i, step in enumerate(route["steps"], 1):
                    if engine.stop_event.is_set():
                        raise Cancelled()
                    engine.event(job, step["label"], i-1)
                    stem = f"web/{i:02d}"
                    item = dict(label=step["label"], passed=True, checks=[], errors=[], evidence=stem+".json")
                    try:
                        game_url(page.url)
                        item["checks"].append(perform(page,step))
                        page.wait_for_timeout(150)
                        game_url(page.url)
                    except Exception as exc:
                        item.update(passed=False, errors=[str(exc).split("Call log:")[0].strip()[:600] or "步骤未通过"])
                    atomic_json(root/item["evidence"], dict(item, action=step))
                    checks.append(item)
                    engine.save(job, checks=list(checks))
                    file = root/(stem+".png")
                    page.screenshot(path=str(file), timeout=6000)
                    shots.append(dict(id=stem,path=stem+".png",label=step["label"],kind="web",width=width,height=height,sha256=sha256(file)))
                    if not item["passed"]:
                        findings.append(dict(id=f"step-{i}",kind="runtime",state="open",severity="medium",title=step["label"],
                            observation=item["errors"][0],impact="路线在这个步骤中断，后续步骤尚未验证。",
                            recommendation="核对当前画面、操作目标与路线约定，调整游戏或步骤后复测。",
                            verify=f"用相同窗口和路线重新运行，确认第 {i} 步通过。",screenshot_id=stem,evidence=item["evidence"]))
                    engine.save(job,screenshots=list(shots),findings=list(findings))
                    if findings:
                        break
            finally:
                browser.close()
        if engine.stop_event.is_set():
            raise Cancelled()
        if findings:
            engine.save(job,status="error",stage="路线未通过",summary=f"第 {len(checks)} 步未通过，失败画面与已完成步骤已保留。")
        else:
            engine.save(job,status="complete",stage="路线全部通过",summary=f"{len(checks)} 个步骤均已通过，已记录 {len(shots)} 张实机画面。")
    except Cancelled:
        engine.save(job,status="cancelled",stage="已停止",summary="试玩已停止，已有操作记录和截图可查看。")
    except Exception as exc:
        engine.save(job,status="error",stage="试玩中断",summary="试玩未完成，已取得的证据保留。",error=str(exc)[:650])
    finally:
        with engine.lock:
            engine.save(job,endedAt=now())
            engine.active=None
