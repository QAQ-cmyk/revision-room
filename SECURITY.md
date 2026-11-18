# Security and data handling

This is a single-user local application. It is not designed to be exposed on a public interface, placed behind a public reverse proxy, or shared between untrusted users.

The HTTP server binds to `127.0.0.1`, checks Host and Origin, and requires a per-process token for mutations. It serves an explicit list of UI assets and recorded evidence. API keys are encrypted for the current Windows user with DPAPI and kept outside the project. Do not treat encryption as isolation from another program running under the same account.

Review exports can contain proprietary screenshots, game names, local build paths, or data that appeared inside a screenshot. The tool does not automatically classify or redact game content. Review an export before publishing it.

Do not attach API keys, encrypted profile files, private builds, or whole `runs/` directories to an issue. For a possible vulnerability, use the repository's private vulnerability reporting feature if enabled. If it is unavailable, open a minimal issue asking for a private contact route without including exploit details or sensitive data.

Report the affected version, the boundary crossed, and a minimal reproduction using the provided fictional demo where possible.
