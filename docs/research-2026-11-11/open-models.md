# Open video, voice and music models for Shortkaar (11 Nov 2026)

This report is based on web research only. Prices are list prices seen on 11 Nov 2026. "Unknown" means I could not verify the point. Third-party sources are marked "(3rd party)".

## What changes our plans

- **Nothing here runs on the laptop.** Every open video model needs an NVIDIA (CUDA) GPU:
  - FramePack needs an RTX 30/40/50 card even at 6 GB ([repo](https://github.com/lllyasviel/FramePack)).
  - MAGI-1 4.5B needs 12-24 GB ([repo](https://github.com/SandAI-org/MAGI-1)).
  - Wan 2.2 S2V needs 80 GB ([card](https://huggingface.co/Wan-AI/Wan2.2-S2V-14B)).

  The Arc A370M (4 GB) noted in CLAUDE.md does not change this. Video therefore means a hosted API or a free cloud GPU.
- **Alibaba's open Wan line stopped at 2.2.** Wan 2.5, 2.6, 2.7 and 3.0 are API-only ([howaiworks](https://howaiworks.ai/blog/alibaba-wan-open-weights-stopped-at-2-2)). The newest open Wan models are Wan2.2-Animate-2 (Aug 2026) and Wan-Dancer (Jul 2026), both Apache 2.0 ([Wan-AI on HF](https://huggingface.co/Wan-AI)).
- **MiniMax H3 (Hailuo 3.0) is the big Chinese open release of 2026.** It is a 33B model that makes video with sound, 4-15 s at a default short side of 768 px ([card](https://huggingface.co/MiniMaxAI/MiniMax-H3)).
  - Its licence excludes the US, EU, UK and South Korea, so Pakistan is allowed. Revenue over $20M needs written permission, and commercial products must show the "MiniMax H3" name ([licence](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)).
  - It speaks 11 languages, and Urdu and Hindi are not among them.
- **fal removes its Wan 2.2 endpoints on 4 Jan 2027.** This includes Animate "move", which the AI singer uses ([fal](https://fal.ai/models/fal-ai/wan/v2.2-14b/animate/move)). WaveSpeed sells the same model at the same $0.04/s at 480p ([docs](https://wavespeed.ai/docs/docs-api/wavespeed-ai/wan-2.2-animate)).
- **Licence alarm on our local voice.** The OmniVoice model card says: "The pre-trained model is licensed under the CC-BY-NC due to constraints from its training data (e.g., Emilia)" ([card](https://huggingface.co/k2-fsa/OmniVoice)). CC-BY-NC means non-commercial use only. CLAUDE.md says commercial use is OK, so that note is out of date.
- **No model publishes Urdu or Hindi lip-sync results.**
  - LongCat-Avatar was evaluated on Chinese and English only ([card](https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5)).
  - MuseTalk lists Chinese, English and Japanese ([repo](https://github.com/TMElyralab/MuseTalk)).

  The safe route is **audio-driven** lip-sync: we make the Urdu voice and the model only moves the lips.
- **The brief has the talkies price under the wrong model.** $0.023/s is Google's Gemini Omni 1.2 Flash at 360p (`toon_motion.py`). fal lists OmniHuman v1.5 at $0.16/s ([fal](https://fal.ai/models/fal-ai/bytedance/omnihuman/v1.5)).

## 1. Video models

All of them can be used on monetised YouTube under the terms shown, and none of them claims ownership of what we generate.

| Model (lab) | Best at | Output | Licence | VRAM / speed | Urdu |
|---|---|---|---|---|---|
| Wan 2.2 A14B T2V/I2V, TI2V-5B (Alibaba) | Best open all-rounder; first+last frame | 480/720p, ~5 s, silent | Apache 2.0, no limits ([Fuser](https://fuser.studio/articles/best-open-source-video-models)) | A14B: 80 GB on one GPU. 5B: an RTX 4090 makes 5 s of 720p in under 9 min ([card](https://huggingface.co/Wan-AI/Wan2.2-S2V-14B)) | - |
| Wan 2.2 S2V-14B | Photo + audio becomes a talking or singing video | 480/720p, as long as the audio | Apache 2.0 | 80 GB+ ([card](https://huggingface.co/Wan-AI/Wan2.2-S2V-14B)) | Driven by the audio; untested |
| Wan2.2-Animate-2 (Aug 2026) | A photo copies the motion of a driving video | 720p | Apache 2.0 | Tuned on 8×A800 ([card](https://huggingface.co/Wan-AI/Wan2.2-Animate-2-14B)) | No audio |
| MiniMax H3 | Top quality, with sound | 768p, 4-15 s, stereo | H3 Community (see above) | Reference setup uses 4 GPUs ([card](https://huggingface.co/MiniMaxAI/MiniMax-H3)) | No |
| HunyuanVideo 1.5 (Tencent, 8.3B) | Efficient T2V/I2V | 480/720p, 1080p via super-resolution | Tencent Community: excludes EU/UK/Korea; 100M monthly users cap; outputs may not train other models ([licence](https://huggingface.co/tencent/HunyuanVideo-1.5/blob/main/LICENSE)) | 14 GB with offload; distilled 480p I2V about 75 s on a 4090 ([card](https://huggingface.co/tencent/HunyuanVideo-1.5)) | - |
| HunyuanVideo-Avatar | Several characters talking; cartoon and anthropomorphic | 704 px, 129 frames | Not named on the card | Unknown ([card](https://huggingface.co/tencent/HunyuanVideo-Avatar)) | Unknown |
| LongCat-Video-Avatar 1.5 (Meituan, May 2026) | Talking avatars, **animals and anime included** | 480/720p, extended by continuation | MIT | Unknown; INT8 option, 8-step distilled ([card](https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5)) | Whisper encoder; tested on Chinese and English only |
| InfiniteTalk (MeiGen) | Dubbing with no length limit, from a photo or a video | 480/720p; fine to about 1 min from a photo | Apache 2.0 | Low-VRAM mode; no figure given ([repo](https://github.com/MeiGen-AI/InfiniteTalk)) | Not stated |
| MultiTalk | Several speakers, singing, cartoons | 480p, up to 15 s | Apache 2.0 | One 4090 in low-VRAM mode ([repo](https://github.com/MeiGen-AI/MultiTalk)) | Not stated |
| FantasyTalking (Alibaba AMAP) | Talking portrait | 512², 81 frames | Apache 2.0 | 40 / 20 / 5 GB; 5 GB runs at 42.6 s per step on an A100 ([repo](https://github.com/Fantasy-AMAP/fantasy-talking)) | Not stated |
| EchoMimic V3 Flash (Ant, Jan 2026) | Light 1.3B talking head and body | Up to 768² | Apache 2.0 | 12 GB ([repo](https://github.com/antgroup/echomimic_v3)) | Not stated |
| MuseTalk 1.5 (Tencent) | Lip-syncs the mouth on an existing video | 256² face area; 30 fps on a V100 | MIT, weights commercial | 4 GB laptop GPU: 8 s of video in ~5 min | Chinese, English, Japanese |
| LivePortrait (Kuaishou) | Expressions and head moves copied from a driving video; humans, cats, dogs | Same size as the source | MIT, but its default InsightFace detector is non-commercial ([note](https://replicate.com/fofr/live-portrait/readme)) | NVIDIA ([repo](https://github.com/KwaiVGI/LivePortrait)) | No audio |
| SkyReels V3 (Skywork) | References become a video; 5-30 s extension; avatars incl. cartoons and animals | 720p; audio up to 200 s | Skywork Community, commercial use allowed ([terms](https://github.com/SkyworkAI/SkyReels-V3/blob/main/LICENSE.txt)) | `--low_vram` flag for cards under 24 GB ([repo](https://github.com/SkyworkAI/SkyReels-V3)) | Chinese, English, Korean named |
| MAGI-1 / 1.1 (Sand AI) | Made chunk by chunk; streaming | 720² default | Apache 2.0 | 4.5B: 24 GB (12 GB quantised). 24B: 4-8 H100s | - |
| Step-Video-T2V (StepFun, 30B) | Long text-to-video | 544×992, 204 frames | MIT | ~78 GB; 743 s on 4 GPUs ([repo](https://github.com/stepfun-ai/Step-Video-T2V)) | - |
| CogVideoX 1.5 (Zhipu) | Small and old | 1360×768, 5-10 s | 2B Apache; 5B has its own licence | 7-10 GB; ~550 s on an H100 ([repo](https://github.com/zai-org/CogVideo)) | - |
| Open-Sora 2.0 (11B) | Research | 768 px, ≤125 frames | Apache 2.0 | 52-60 GB; 1,656 s on one H100 ([repo](https://github.com/hpcaitech/Open-Sora)) | - |
| FramePack | 60 s image-to-video on 6 GB | Long | Apache 2.0 | 1.5-2.5 s per frame on a 4090 | - |
| LTX-2.5 (Lightricks, Aug 2026) | Video and its sound in one pass; up to 20 s; up to 4K | 720p-4K | Free under $10M revenue ([Fuser](https://fuser.studio/articles/best-open-source-video-models)) | 16 GB ([Rundown](https://www.therundown.ai/tools/ltx-2)) | Languages not listed |
| Mochi 1 (Genmo) | Older 10B model | 480p | Apache 2.0 | 60 GB; under 20 GB in ComfyUI ([repo](https://github.com/genmoai/mochi)) | - |

### Cheapest hosted prices

| Model | Price (480p unless noted) | Where |
|---|---|---|
| Wan 2.2 I2V | **$0.015/s** (flash); $0.036/s at 720p | DashScope Singapore ([pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing)) |
| | $0.05 per 5 s (ultra-fast) | [WaveSpeed](https://wavespeed.ai/models/wavespeed-ai/wan-2.2/i2v-480p-ultra-fast) |
| | $0.05 per video; $0.11 at 720p | Replicate fast ([blog](https://replicate.com/blog/wan-22), [Pruna](https://www.pruna.ai/blog/wan-2-2-video-juiced-fastest-and-cheapest-video-generation)) |
| | $0.04/s; $0.08 at 720p; leaves 4 Jan 2027 | [fal](https://fal.ai/models/fal-ai/wan/v2.2-a14b/image-to-video) |
| | $0.09 per 5 s | Novita ([blog](https://blogs.novita.ai/wan-2-2-vs-veo-3-which-is-the-better-match-for-you/)) |
| | $0.29 per video | SiliconFlow ([guide](https://www.siliconflow.com/articles/cheapest-video-multimodal-models)) |
| Wan 2.2 S2V | $0.10/s; $0.20 at 720p; leaving | [fal](https://fal.ai/models/fal-ai/wan/v2.2-14b/speech-to-video) |
| | $0.072/s, Beijing region only | DashScope |
| Wan 2.2 Animate | $0.04/s; $0.08 at 720p | WaveSpeed, and fal until 4 Jan |
| | $0.12/s | DashScope (animate-move) |
| Wan 2.6 i2v-flash (closed) | 720p: $0.025/s silent, $0.05/s with sound. **Takes our own 3-30 s audio and syncs the lips to it** ([API](https://www.alibabacloud.com/help/en/model-studio/image-to-video-api-reference)) | DashScope |
| Wan 3.0 (closed) | $0.05/s; 30 s free quota | DashScope |
| MiniMax H3 Max | $0.05/s; 768p $0.08/s (from 16 Nov) | [fal](https://fal.ai/models/minimax/h3-max/image-to-video) |
| MiniMax H3 | from $0.04/s | [WaveSpeed](https://wavespeed.ai/pricing) |
| HunyuanVideo 1.5 | $0.075/s | [fal](https://fal.ai/models/fal-ai/hunyuan-video-v1.5/image-to-video) |
| | Unknown | Tencent Cloud (official) |
| InfiniteTalk | **$0.03/s**; $0.06 at 720p; 3 s minimum; up to 10 min | [WaveSpeed](https://wavespeed.ai/models/wavespeed-ai/infinitetalk) |
| | $0.20/s, deprecated | [fal](https://fal.ai/models/fal-ai/infinitalk) |
| LongCat Avatar | $0.15/s; $0.30 at 720p | [fal](https://fal.ai/models/fal-ai/longcat-multi-avatar/image-audio-to-video) |
| LTX-2.5 Fast | $0.09/s at 720p | [fal](https://fal.ai/models/lightricks/ltx-2.5/image-to-video/fast) |

## 2. Voice, music, images, upscaling

| Model | Urdu / Hindi | Licence | On CPU? | Hosted price |
|---|---|---|---|---|
| **Indic Parler-TTS** (AI4Bharat, 0.9B) | **Urdu and Hindi officially supported**, 69 voices | Apache 2.0 | Falls back to CPU; speed unknown ([card](https://huggingface.co/ai4bharat/indic-parler-tts)) | - |
| OmniVoice (installed) | Urdu works in our own tests | **Weights CC-BY-NC** | Yes, ~5.4× real time (CLAUDE.md) | - |
| CosyVoice 3 | 9 languages plus Chinese dialects; no Urdu or Hindi (3rd party, [tts.ai](https://tts.ai/voices/cosyvoice3/)) | Apache 2.0 | Unknown | $0.13 per 10k characters, 10k free (DashScope) |
| IndexTTS2 | Chinese and English (3rd party) | Bilibili licence with thresholds (3rd party, [tts.ai](https://tts.ai/voices/indextts2/)) | Unknown | - |
| Fish Audio S2 Pro | 80+ languages; Urdu not named | Research licence; commercial use needs a deal ([Fish](https://fish.audio/s2/)) | - | - |
| F5-TTS / Spark-TTS | - | CC-BY-NC ([card](https://huggingface.co/SWivid/F5-TTS)) / CC BY-NC-SA (3rd party) | - | - |
| Chatterbox Multilingual | Hindi yes, Urdu no ([README](https://huggingface.co/ResembleAI/chatterbox/blob/main/README.md)) | MIT | Unknown | - |
| **ACE-Step 1.5** (Jan 2026) | "50+ languages", list not published | MIT | Lists CPU and Intel XPU; under 4 GB VRAM; under 10 s a song on an RTX 3090; 10 s-10 min songs ([repo](https://github.com/ace-step/ACE-Step-1.5)) | Official HF Space is built for ZeroGPU ([Space](https://huggingface.co/spaces/ACE-Step/Ace-Step-v1.5)) |
| YuE2 | Not listed | Weights CC BY-NC, but individual creators may monetise outputs | Needs 24 GB NVIDIA ([repo](https://github.com/multimodal-art-projection/YuE)) | - |
| DiffRhythm 1.2 | Not listed | Apache 2.0 | 8 GB; songs up to 285 s ([repo](https://github.com/ASLP-lab/DiffRhythm)) | - |
| WanSong (Alibaba, Jul 2026) | "Multilingual" | Weights not confirmed open ([paper](https://huggingface.co/papers/2607.14749)) | - | - |
| **Z-Image Turbo** (Alibaba, 6B) | Renders English and Chinese text only | Apache 2.0 | Needs 16 GB ([card](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)) | **$0.005 per megapixel ≈ $0.01 per 1080×1920** ([fal](https://fal.ai/models/fal-ai/z-image/turbo)) |
| Qwen-Image 2.0 / 2.1 | - | 2.0 is Apache (3rd party). 2.1 (Sep 2026) is **research-only** ([report](https://runtimewire.com/article/alibaba-qwen-image-2-1-transparent-editing-research-license)) | - | - |
| Real-ESRGAN / RIFE (ncnn) | - | BSD-3 / MIT | Run on Intel through Vulkan ([1](https://github.com/xinntao/Real-ESRGAN), [2](https://github.com/nihui/rife-ncnn-vulkan)); both already in use | - |
| SeedVR2 (ByteDance) | - | Apache 2.0 ([Comfy](https://docs.comfy.org/tutorials/utility/seedvr2)) | GPU only | $0.001 per megapixel of video; 1080p × 121 frames = $0.25 ([fal](https://fal.ai/models/fal-ai/seedvr/upscale/video)) |

I did not research HunyuanImage and FLUX in depth. Z-Image covers that need.

## 3. Free compute

| Platform | Free amount | Scriptable and allowed to run unattended? |
|---|---|---|
| Kaggle | About 30 GPU h/week (a floating quota, not documented); 12 h sessions; P100 or 2×T4 ([gpuperhour](https://gpuperhour.com/blog/free-cloud-gpus-and-credits)) | Yes: `kaggle kernels push` uploads **and runs** a notebook ([API docs](https://raw.githubusercontent.com/Kaggle/kaggle-api/main/docs/kernels.md)). Rules on bot use: unknown. On a T4, Wan 2.2 makes 5 s of 480p in about 13 min ([3rd party](https://penioj.blogspot.com/2025/08/how-to-use-wan22-google-colab-notebooks.html)) |
| Colab free | Limits not published; up to 12 h | **No.** Free runtimes forbid remote control and "bypassing the notebook UI" ([FAQ](https://research.google.com/colaboratory/faq.html)) |
| HF ZeroGPU | 2 min/day without login; **5 min/day** on a free account; **40 min/day** on PRO ($9/mo); extra time $1 per 10 min; half an RTX Pro 6000 (48 GB) ([docs](https://huggingface.co/docs/hub/spaces-zerogpu)) | Yes, through `gradio_client`. Pass `hf_token` or the quota is not yours ([forum](https://discuss.huggingface.co/t/guidance-on-using-zero-token-and-gradio-api-together/131070)). A free account may host 2 ZeroGPU Spaces of its own |
| Modal | **$30/month** credit. L4 $0.000222/s, A100-80GB $0.000694/s, H100 $0.001097/s ([pricing](https://modal.com/pricing)) | Yes; it is built for scripts |
| Lightning AI | The monthly credit may have become a one-time grant in Sep 2026: unverified ([log](https://www.usagepricing.com/blueprint/activity/lightning-ai-2026-09-21-gpu-rate-card-reprice)) | Unknown |
| Alibaba Model Studio | Free for 90 days: Wan 3.0 30 s, Wan 2.1 T2V 50 s, TTS 10k characters ([pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing)) | API |
| WaveSpeed | $1 credit, no card ([pricing](https://wavespeed.ai/pricing)) | API |
| SiliconFlow | Free models are text-only and change over time; I found no free video tier ([docs](https://docs.siliconflow.com/en/faqs/misc_rate)) | API |

**What this means:** renting a GPU for video costs more than an API. An A100 for 9 minutes is about $0.10-0.37, against $0.075 for a 5 s 480p Wan clip on DashScope. Free GPU time is worth it only for models nobody sells cheaply, such as ACE-Step 1.5 and Indic Parler-TTS.

## 4. Recommendations

**Do first, at no cost:** stop using OmniVoice on monetised channels. Test **Indic Parler-TTS** (Apache 2.0, official Urdu) on the CPU as the fallback after edge-tts.
- Risk: its Urdu quality and CPU speed are unknown.
- Risk: the download is gated, so it needs a free HF login.

Ranked by quality gain × cost:

1. **Moving hook shots.** For the night/horror stories, history and the AI songs, animate the first 1-2 shots of each Short with **Wan 2.2 I2V flash at 480p** on DashScope ($0.015/s) or WaveSpeed ultra-fast ($0.05 per 5 s). Upscale on the laptop with the Real-ESRGAN and RIFE we already have.
   - Cost: **about $0.08-0.15 per Short.**
   - Risk: an Alibaba Cloud account from Pakistan is untested.
   - Risk: never animate real people or sacred figures.
   - Risk: YouTube's rules against repetitive AI content.
2. **Real Urdu lip-sync for the talkies channel.** Our edge-tts makes the Urdu voice and **InfiniteTalk on WaveSpeed** ($0.03/s at 480p, Apache weights) moves the lips.
   - Cost: **about $0.75-0.90 per 25-30 s Short.**
   - Fallback: Wan 2.6 i2v-flash with our own audio (`audio_url`, $0.05/s at 720p, closed model).
   - Animals: LongCat-Avatar, which names animals, costs $0.15/s on fal.
   - Risk: lip accuracy on animal muzzles and in Urdu is untested.
   - Risk: Gemini Omni ($0.023/s at 360p) is cheaper, but needs Gemini credit and its docs say other languages are "not evaluated".
3. **Cheaper stills with Z-Image Turbo on fal.** It costs about **$0.01 per 1080×1920 image**, against about $0.067 for today's 1K Gemini picture. Use it for history, horror, toons and the singer's stills.
   - Saving: **about $0.80 on each long video that uses 14 AI pictures.**
   - Risk: no Urdu text in the picture, so keep overlaying text with PIL.
   - Risk: keeping a recurring character consistent is unknown.
4. **AI songs at close to zero cost.** Run **ACE-Step 1.5 turbo** (MIT) on our own ZeroGPU Space (5 min/day free, or $9/mo for 40 min) or on Modal's $30 credit. Today's Lyria costs $0.08-0.10 a song.
   - Cost: **under $0.01 a song** (estimate, from <10 s a song on an RTX 3090).
   - In the same change, move the singer's Wan Animate calls from fal to WaveSpeed. The price is the same, and fal retires the endpoint on 4 Jan 2027.
   - Risk: Urdu and Hindi lyric quality is unpublished, so run an A/B test against Lyria first.
   - Risk: ZeroGPU queues.
5. **Kaggle as a free overnight GPU.** Push a notebook each night with `kaggle kernels push` to render queued 480p Wan 2.2 clips (GGUF and lightx2v versions).
   - Cost: **$0.** At ~13 min a clip, 30 h is roughly 130 clips a week.
   - Risk: the quota floats and is undocumented.
   - Risk: Kaggle's rules on automation are unclear.
   - Risk: there is no same-day guarantee.

**Leave as they are:** Quran (no generated imagery near recitation), cricket and controversies (likeness of real people) and Punchline Bazaar (source clips).
