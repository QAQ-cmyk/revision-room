"""Build an offline, self-contained interactive demo. Uses only original fixtures."""
import base64
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def inline_json(value):
    return json.dumps(value,ensure_ascii=False).replace("<","\\u003c")


def main():
    web=ROOT/"web"
    page=(web/"index.html").read_text(encoding="utf-8")
    report=json.loads((web/"demo"/"report.json").read_text(encoding="utf-8"))
    images={name:"data:image/png;base64,"+base64.b64encode((web/"demo"/name).read_bytes()).decode() for name in ["hud.png","inventory.png"]}
    css=(web/"style.css").read_text(encoding="utf-8")
    js=(web/"app.js").read_text(encoding="utf-8")
    svg=(web/"favicon.svg").read_text(encoding="utf-8")
    icon="data:image/svg+xml;base64,"+base64.b64encode(svg.encode("utf-8")).decode()
    page=page.replace('href="/favicon.svg"',f'href="{icon}"').replace('href="/" aria-label="修订室首页"','href="#main" aria-label="修订室首页"')
    page=page.replace('<link rel="stylesheet" href="/style.css">',"<style>"+css+"</style>")
    page=page.replace('  <script src="/app.js" defer></script>\n',"")
    data="window.REVISION_ROOM_DEMO="+inline_json(report)+";window.REVISION_ROOM_IMAGES="+inline_json(images)+";"
    page=page.replace("</body>","<script>"+data+js+"</script></body>")
    folder=ROOT/"docs";folder.mkdir(exist_ok=True)
    (folder/"index.html").write_text(page,encoding="utf-8",newline="\n")
    print("Built docs/index.html (offline demo; no credentials or private game assets)")


if __name__=="__main__":main()
