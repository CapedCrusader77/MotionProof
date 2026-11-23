# AI assistant

An optional explanation panel on the Reports screen: you ask a question about an experiment and a
language model answers from a summary of its stored results. MotionProof works fully without it.
Every number in the application comes from the engineering engine, never from the model.

## Providers

| Provider | Setting | Key | Where the data goes |
|---|---|---|---|
| Local (default) | `MOTIONPROOF_AI_PROVIDER=ollama` | none | Your own [Ollama](https://ollama.com) server; nothing leaves the machine |
| Anthropic (Claude) | `MOTIONPROOF_AI_PROVIDER=anthropic` | `MOTIONPROOF_AI_KEY` | `api.anthropic.com` |
| OpenAI or compatible | `MOTIONPROOF_AI_PROVIDER=openai` | `MOTIONPROOF_AI_KEY` | `api.openai.com`, or the host in `MOTIONPROOF_AI_BASE_URL` |

Set the variables in the environment of the process that runs `motionproof serve`, then restart
it. For example, in PowerShell:

```powershell
$env:MOTIONPROOF_AI_PROVIDER = "anthropic"
$env:MOTIONPROOF_AI_KEY = "<your key>"
uv run motionproof serve --home workspace
```

| Variable | Meaning |
|---|---|
| `MOTIONPROOF_AI` | `off` disables the assistant completely |
| `MOTIONPROOF_AI_PROVIDER` | `ollama` (default), `anthropic` or `openai` |
| `MOTIONPROOF_AI_KEY` | API key for the cloud providers |
| `MOTIONPROOF_AI_MODEL` | Model name. Anthropic defaults to `claude-sonnet-5-5`; `openai` needs one; for Ollama the first installed model is used |
| `MOTIONPROOF_AI_BASE_URL` | OpenAI-compatible endpoint, default `https://api.openai.com/v1`. Must be `https` unless it is `localhost` |
| `MOTIONPROOF_AI_DAILY_LIMIT` | Cloud questions per account per day (UTC), default 30 |
| `OLLAMA_HOST` | Ollama address, default `http://127.0.0.1:11434` |

Settings, System, Optional AI shows what is configured, and the Reports panel shows it next to
the question box.

## What is sent to a cloud provider

Only the question and a summary of one experiment's stored results: experiment and model names,
sampling and task settings, scenario counts, constraints and their pass rates, failure categories,
metric quantiles, the top ranked tolerances, and the assumptions and limitations lists. No CAD or
mesh files, no account details, no other projects. The Reports panel states this and names the
host before you ask, and each answer repeats where it was sent.

## The key

* It is read from the server's environment on each request. It is never stored in the workspace
  or the database, never sent to the browser, and never included in a response, a status or an
  error message (provider error text is not passed on, because providers can echo part of a key).
* Do not put it in a file inside the repository. Anyone who can set variables for the server
  process can use it; the accounts of the web app cannot read it.
* A key is only ever sent over `https`.

## Cost control

Each cloud question counts against the account's daily limit before it is sent, and the question
is refused with HTTP 429 once the limit is reached, so a loop cannot run up a bill. The local
provider is not limited. Your provider's own spending limits still apply on top.

## How the answers are kept honest

The model is instructed to use only numbers that appear in the summary and to quote them exactly,
to cite the constraint, metric or parameter behind each statement, never to call a design safe or
validated, and to say so when the evidence does not answer the question. Answers are shown as
generated text with that disclaimer. They are not checked automatically: read them against the
evidence.
