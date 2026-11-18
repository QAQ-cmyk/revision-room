# AI 接口配置 / Vision providers

每个接口都需要你自己的服务商账户。模型名请从该账户的控制台复制，并确认支持图片输入；项目不固定一个可能过期的“最新模型”。

| Preset | Base URL | Transport |
| --- | --- | --- |
| Grok | `https://api.x.ai/v1` | OpenAI-compatible Chat Completions |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | OpenAI-compatible Chat Completions |
| Claude | `https://api.anthropic.com/v1` | Native Messages |
| 通义千问 / Qwen | Copy your workspace and region endpoint from Model Studio / 百炼 | OpenAI-compatible Chat Completions |
| OpenAI API | `https://api.openai.com/v1` | Chat Completions, `max_completion_tokens` |
| Custom | Your compatible provider's base URL | Select the appropriate transport |

Do not append `/chat/completions`, `/messages`, or `/responses` to the base URL. Remote URLs must use HTTPS. Loopback servers such as `http://127.0.0.1:1234/v1` may use HTTP and **本机服务无需密钥**. Local models must also support images and the requested JSON format.

## 配置步骤

1. 打开 **管理 AI 接口**，选服务商，填写便于区分的名称。
2. 确认基础地址，填入模型名与 API 密钥。千问需填当前工作空间和地域对应的地址。
3. 点击 **测试看图**。程序发送一张双色图片，检查模型返回的左右颜色是否正确。本次只验证基本图片理解与连接，不保证完整评审质量。
4. 点 **保存并选用**。可保留最多 12 套配置，在首页切换。

编辑已保存接口时，密钥留空表示保留；更换地址或接口格式则必须重新填写密钥，避免把旧密钥发给新服务。关闭设置窗口会清空输入框。保存操作本身不调用模型。

Each review records the provider display name and model actually selected for that run. Switching the current profile does not rename old reports. Only the selected profile receives a request; this version does not query multiple models automatically.

## 故障提示

| Message / symptom | What to check |
| --- | --- |
| 401 / 403 | Correct provider key, account access, and region |
| 404 | Base URL and model ID; remove the endpoint suffix |
| 429 | Provider quota, balance, or rate limits |
| Incorrect test colors | The selected model may not accept or understand image input |
| Invalid or incomplete JSON | Use a model able to follow a JSON schema; increase the output limit if truncated |
| Request timed out | Network/provider availability; review requests time out after about 3 minutes |

There is no automatic retry or fallback to another provider. Screenshots are kept when a review is incomplete. If a model truncates its output, an incomplete list is not presented as a successful review.

## Codex 登录方式

安装并登录本机 Codex CLI 后，首页可以选择 **Codex · 本机登录**。程序检查登录状态，把指定截图交给只读评审进程，禁用其命令执行、浏览器和派工能力。它不会把登录凭据转换成 OpenAI API Key。

The Codex integration was checked locally with CLI `0.169.0-alpha.11.1`; older builds may lack the required isolation flags. An incompatible CLI should produce an incomplete-review message while keeping evidence. If you prefer a provider API, select its saved profile instead.

## Official API references

The transports were implemented against these official references; individual provider models were not live-tested with user credentials in this release.

- [xAI Chat Completions](https://docs.x.ai/developers/rest-api-reference/inference/chat-completions)
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Claude Messages](https://platform.claude.com/docs/en/api/messages)
- [Qwen vision through the OpenAI-compatible interface](https://www.alibabacloud.com/help/en/model-studio/qwen-vl-compatible-with-openai)
- [OpenAI vision inputs](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)
