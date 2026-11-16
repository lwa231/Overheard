# Local worker models: GPU choice, model fit, serving (as of 2026-11-11)

Sources: [IL12] https://insiderllm.com/guides/what-can-you-run-12gb-vram/ (updated 2026-10-15)
[BL16] https://bestllmfor.com/guides/best-local-llm-16gb-vram/ (data 2026-11-11)
[L1T] https://forum.level1techs.com/t/converting-a-data-center-gpu-for-desktop-use/250919?page=4 (forum posts, anecdotal)
Many figures come from SEO-style benchmark sites and forum posts. Re-measure on your own box. "ASSUMPTION" = not verified this session.

## 1. GPU: RTX 3060 12 GB vs Instinct MI25 16 GB
| | RTX 3060 12 GB | MI25 16 GB |
|---|---|---|
| Runtime | CUDA, first-class in llama.cpp, Ollama, vLLM, Linux driver (ASSUMPTION) | Vega 10 = gfx900. Forum poster says AMD re-added gfx900 in ROCm 7.13 [L1T], unverified; officially dropped earlier (ASSUMPTION). Reliable path = llama.cpp Vulkan (RADV) [L1T] |
| Speed | ~30 tok/s on 9B-14B Q4-Q6 single stream [IL12] | 40-70 tok/s on many 9B-26B models, gpt-oss-20B ~70, Qwen3.6-35B-A3B 86-110 (Vulkan, anecdotal) [L1T]; CPU offload "slows dramatically" [L1T] |
| Ollama / vLLM | Both work (ASSUMPTION) | Ollama ROCm path unlikely on gfx900; vLLM unsupported (ASSUMPTION) |
| Cooling | Active fans | Passive server card: needs a 3D-printed shroud + blower and a fan-control service; early overheat reported when fan script started too early [L1T] |
| Power | ~170 W (ASSUMPTION) | 220 W flashed BIOS reported [L1T]; 6+8-pin boards have weaker VRMs than 8+8 [L1T] |
| Display | HDMI/DP | No outputs (ASSUMPTION). Ryzen 5 2600 has no iGPU, so you would need a second cheap GPU for boot/flash/console; 7600 has an iGPU |
| Setup risk | Plug in, `apt install nvidia-driver-*` | Workstation vBIOS flash (WX9100 + edited pptable, AVFS must be re-enabled or voltage/power run high [L1T]); needs Above-4G decoding (ASSUMPTION); bricking possible |
| Used price | ~$300 ($200-400) [IL12] | not sourced |

Recommendation: buy the RTX 3060 12 GB. The MI25 gives 4 GB more VRAM and often higher tok/s on paper, but you take on a flash, a cooling build, a second display GPU, and an ecosystem (Vulkan only, realistically) that can break on updates. For an unattended server serving other agents, boring wins.
Better value, if budget allows: a 16 GB NVIDIA card (RTX 4060 Ti 16GB ~18 tok/s and 5060 Ti 16GB ~22 tok/s on Mistral Small 24B Q4_K_M [BL16]; prices not sourced). A used RTX 3090 24 GB is the real upgrade but listed at $1,400-1,550 in Oct 2026 [IL12], so not value.

## 2. What fits
Rule of thumb (ASSUMPTION, standard): GGUF file GB ~= params(B) x bits/8. Q4_K_M ~0.6 GB per B, Q6_K ~0.82, Q8_0 ~1.06. Add KV cache (grows with context x parallel slots) plus ~1 GB runtime overhead. Keep weights <= ~75% of VRAM if you want multiple slots. Sizes below are the sources' VRAM figures unless marked.

12 GB (3060):
| Model | Quant | Size | Context that fits | Suits |
|---|---|---|---|---|
| Qwen 3.5 9B | Q6_K | ~9.5 GB [IL12] | 8-16K [IL12] | general, extraction, vision; ~30 tok/s |
| Qwen 3.5 9B | Q4_K_M | ~5.5 GB (ASSUMPTION) | 16-32K across slots | default 2-4 slot worker |
| Qwen 2.5 14B | Q4_K_M | ~9 GB [IL12] | 4-8K [IL12] | best quality at this tier, code; ~30 tok/s |
| Qwen2.5-Coder 14B (ASSUMPTION a newer Qwen coder may exist; check HF) | Q4_K_M | ~9 GB (ASSUMPTION) | 4-8K | simple code, edits |
| Gemma 4 12B | Q4_K_M | 7 GB [BL16] | 16K with ~4 GB KV [BL16] | summaries, drafts |
| Mistral Nemo 12B | Q4_K_M | ~8 GB [IL12] | 128K native, few K in VRAM | general, ~32 tok/s |
| Llama 3.1 8B (fast, high concurrency) | Q4_K_M / Q6_K | ~5 / 6.5 GB [IL12] | 8K x 3-4 slots | tagging, classification; ~35 tok/s |
| Embedding: nomic-embed-text v1.5 or Qwen3-Embedding-0.6B (ASSUMPTION) | Q8_0 / F16 | 0.3-0.7 GB (ASSUMPTION) | 2-8K | embeddings; run as 2nd `llama-server --embedding` or on CPU |
| Qwen 3.6 35B-A3B MoE (`--n-cpu-moe`) | Q4 | ~20 GB (ASSUMPTION) | n/a | ~38 tok/s on a 3060 [IL12], but needs >=32 GB RAM; not on 16 GB |

16 GB (MI25 or 16 GB NVIDIA) adds:
| Model | Quant | Size | Notes |
|---|---|---|---|
| Qwen 3.5 9B | Q8_0 | ~11 GB [BL16] | 32K (64K with Q8 KV) [BL16] |
| Mistral Small 24B | Q4_K_M | 14 GB [BL16] | general; "tight", 1-2 slots only |
| Devstral Small 2 24B | Q4_K_M | 14 GB [BL16] | coding agent; tight |
| gpt-oss 20B | MXFP4 | 13 GB [BL16] | speed + 131K context [BL16]; fast MoE |
| Granite 4.2 8B | Q8_0 | 9 GB [BL16] | extraction/enterprise-style tasks |

Not verified: current best Qwen coder name/size, current small (3-4B) models, embedding model status. Check Hugging Face trending (search "GGUF", sort by trending/downloads) before downloading.

## 3. Abliterated / uncensored variants
Community fine-tunes or weight edits of the same base models: identical size, quant and VRAM maths; quality (instruction following, reasoning) can drop and they are unofficial. Prefer a stock model unless refusals actually block a task.

## 4. RAM
- 16 GB is enough if the whole model sits in VRAM (OS + server ~2-3 GB, ASSUMPTION). It is not enough for MoE expert offload or >14B models spilling to CPU.
- Swap/zram on NVMe helps loading and prevents OOM kills (mmap'd GGUF pages can be evicted and re-read). It does not speed inference; any weight read per token from swap is catastrophic. Use zram (cheap) plus a modest NVMe swap file as safety only (ASSUMPTION).
- Partial CPU offload: speed falls toward system-RAM bandwidth (DDR4 dual-channel ~40-50 GB/s vs ~360 GB/s on the 3060; ASSUMPTION), hence the "dramatic slowdown" reports [L1T]. Exception: MoE expert offload [IL12]. A 7600 with DDR5 offloads faster than a 2600 with DDR4 (ASSUMPTION).
- Target: 32 GB (2x16) now; 64 GB only if you want 30B+ MoE offload. Keep model files on the fast NVMe for load time.

## 5. Serving
- Recommended: llama.cpp `llama-server` (OpenAI-compatible API, continuous batching, `-np` slots, `-fa`, quantised KV `-ctk q8_0 -ctv q8_0`, `-hf repo:quant` pulls from Hugging Face). Run under systemd. Example (ASSUMPTION, verify flags): `llama-server -m model.gguf -ngl 99 -c 24576 -np 3 -fa on --host 0.0.0.0`.
- `-c` is divided across slots, so 24576 / 3 = 8K each. Total context x model KV cost must fit beside the weights.
- Ollama: simpler model swapping (`OLLAMA_NUM_PARALLEL`), a bit less control; fine to start. vLLM: poor fit for 12 GB (large overhead, GGUF support weaker; ASSUMPTION) and unusable on MI25.
- Realistic on 12 GB: 9B Q4 with 3-4 slots x 8K, or 14B Q4 with 2 slots x 4-6K. Aggregate throughput rises with batching but per-request speed drops (ASSUMPTION; measure with `llama-bench` and a 3-client load test).
- Two processes if needed: one chat model, one tiny embedding server.

## 6. Bottom line
1. Buy the RTX 3060 12 GB (~$300 used [IL12]); skip the MI25 (flash, shroud, extra display GPU, Vulkan-only).
2. Upgrade RAM to 32 GB; keep GGUFs on NVMe.
3. Install the NVIDIA driver + llama.cpp (CUDA build), `llama-server` as a systemd service with 3 slots.
4. Start with Qwen 3.5 9B Q4_K_M (workhorse), Qwen 2.5 14B Q4_K_M (quality/code), Llama 3.1 8B (bulk tagging) + an embedding model; benchmark and drop what the boss never uses.
5. If budget stretches, a 16 GB RTX 4060 Ti/5060 Ti beats both options for fit (24B models) without the MI25 hassle.
