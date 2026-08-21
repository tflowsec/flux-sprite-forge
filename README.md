# flux-sprit-forge

Agent skills for game-ready 2D sprites, layered maps, and engine-ready prototypes — **powered by the [FLUX API](https://docs.bfl.ai) from Black Forest Labs**.

Ask in natural language. The agent plans the asset pipeline, generates raw visuals through the FLUX image/video API, then deterministic local processors clean, split, validate, and export assets for Godot, Unity, or raw 2D game workflows.

> Ported from [0x0funky/agent-sprite-forge](https://github.com/0x0funky/agent-sprite-forge) (MIT). The original targets Codex / Grok built-in image generation; this fork replaces the generation backend with the FLUX REST API so it runs on **any agent** (Claude Code, Codex, Cursor, ...) with a `BFL_API_KEY`. All pipeline design, QC discipline, and post-processing credit belongs to the upstream project.

## What Makes It Different

Agent Sprite Forge is not just a folder of prompts. It is an agent-first 2D game asset workflow where the agent decides the plan, FLUX creates the raw visuals, and deterministic scripts turn those visuals into reusable game assets.

|  |  |  |  |
| --- | --- | --- | --- |
| **Sprite sheets**  Characters, monsters, props, attacks, spells, projectiles, impacts, idles, walks, and reference-guided variants. | **Layered maps**  Ground-only bases, dressed references, prop packs, transparent props, y-sort placement, collision, zones, and previews. | **Engine handoff**  Godot scenes, editable TileMap layers, separated props, encounter grass, collision bodies, exits, and debug players. | **Local cleanup**  Chroma-key removal, frame extraction, alignment, transparent PNG/GIF export, prop-pack slicing, and QA metadata. |

## Included Skills

| Skill | Use it for | Output | Generation |
| --- | --- | --- | --- |
| `generate2dsprite` | Sprites, animation sheets, props, spell bundles, FX, reference variants, optional layout guides for fixed-frame sheets | Raw sheet, cleaned transparent sheet, frames, GIFs, metadata | FLUX.2 (`flux_generate.py`) |
| `generate2dmap` | Baked maps, layered raster maps, clean HD RPG maps, prop packs, collision/zones, Godot-editable scenes | Base map, dressed reference, prop pack, extracted props, preview, scene metadata | FLUX.2 (`flux_generate.py`) |
| `video2dsprite` | **Denser motion sprites from video**: base still → FLUX 3 image-to-video → frame extract → magenta chroma → multi-density sprite strips/GIFs | Video, raw/clean frames, 8/16/24/48 sprite sets, strips, preview GIFs | FLUX.3 video (`flux_video.py`) |

## Requirements

- Python 3.10+, `Pillow`, `numpy`
- `ffmpeg` on `PATH` (only for `video2dsprite` frame extraction)
- A BFL account with credits and `BFL_API_KEY` exported (1 credit = $0.01)

## API Key Setup

1. Register at https://dashboard.bfl.ai and add credits (start with $10-20).
2. Create an API key under **API → Keys**.
3. Export it:

```bash
export BFL_API_KEY="bfl_..."        # bash / zsh
setx BFL_API_KEY "bfl_..."          # Windows (new terminal)
```

Keep the key out of prompts, logs, and committed files. Result URLs from the API expire within minutes; the helper scripts download immediately.

## Install

Clone the repo, install Python dependencies, then copy skills into your agent's skills directory.

### Option 1: Windows PowerShell

```powershell
git clone https://github.com/tflowsec/flux-sprit-forge.git
cd .\flux-sprit-forge
python -m pip install -r .\requirements.txt

# Claude Code
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".\skills\*" "$env:USERPROFILE\.claude\skills\"
```

### Option 2: macOS / Linux

```bash
git clone https://github.com/tflowsec/flux-sprit-forge.git
cd ./flux-sprit-forge
python3 -m pip install -r ./requirements.txt

# Claude Code
mkdir -p ~/.claude/skills
cp -R ./skills/* ~/.claude/skills/
```

For other agents, copy `skills/*` into the equivalent skills directory. Start a new session after installation so skills reload.

## Model Routing and Cost

`flux_generate.py` defaults to `flux-2-klein-9b`; override with `--model`.

| Model | Flag value | 1MP T2I | Best for |
| --- | --- | --- | --- |
| FLUX.2 [klein] 9B | `flux-2-klein-9b` | $0.015 | Iteration, QC loops, drafts (default) |
| FLUX.2 [pro] | `flux-2-pro` | $0.03 | Accepted/final art (default for finals) |
| FLUX.2 [max] | `flux-2-max` | $0.07 | Hero and main-character art |
| FLUX.2 [flex] | `flux-2-flex` | $0.05 | Precise in-image text, adjustable controls |

All FLUX.2 models support image editing and multi-reference composition through `input_image` / `input_image_2` ... `input_image_8` (up to 8 on pro/max/flex, 4 on klein) — reference images by number in the prompt: "the character from image 1 in the environment from image 2". For video, iterate with `--draft` and enhance the chosen cache before shipping.

See https://bfl.ai/pricing for full details.

## How It Works

1. The user asks the agent for a sprite, prop pack, map, or engine-ready prototype.
2. The agent chooses the asset type, action, bundle shape, sheet layout, frame count, style, and alignment strategy.
3. `flux_generate.py` / `flux_video.py` submit the job to the FLUX API, poll, and download the raw visual asset.
4. Local scripts run deterministic post-processing: chroma-key cleanup, despill, frame extraction, alignment, prop-pack slicing, GIF/PNG export, and validation metadata.
5. For maps and prototypes, the agent can also assemble placement metadata, collision, trigger zones, Godot scenes, or Unity project wiring.

The script is not the creative brain. The agent makes the visual and pipeline decisions; the FLUX API renders; the Python tools only perform repeatable pixel and export operations.

## Suggested Prompts

### Sprite

```
Use $generate2dsprite to create a 3x3 idle for an ultimate earth titan.
```

```
Use $generate2dsprite to create a wizard spell bundle with cast, projectile, and impact sprites.
```

### Video → dense sprites

```
Use $video2dsprite with my existing side-view hero PNG as base. Generate a 6s in-place run on #FF00FF, extract frames, chroma key, and export 8/16/24/48 sprite sets + preview GIFs. Do not wire into the game; just report paths.
```

### Map

```
Use $generate2dmap to create a top-down RPG forest shrine map. Use a layered raster pipeline, a 3x3 prop pack for small environmental props, precise collision, encounter grass zones, a rest point, and actors that can walk in front of and behind tall props.
```

```
Use $generate2dmap to create a Godot-editable RPG map with separated props, encounter grass Area2D zones, collision StaticBody2D blockers, exit zones, and a debug player scene.
```

## Repository Layout

```
flux-sprit-forge/
  README.md
  requirements.txt
  skills/
    generate2dsprite/
      SKILL.md
      references/
        modes.md
        prompt-rules.md
      scripts/
        flux_generate.py        # FLUX image API transport
        generate2dsprite.py     # postprocess primitive
        make_layout_guide.py
        make_anchor_layout.py
    generate2dmap/
      SKILL.md
      references/
        layered-map-contract.md
        map-strategies.md
        prop-pack-contract.md
      scripts/
        flux_generate.py        # FLUX image API transport (shared copy)
        compose_layered_preview.py
        extract_prop_pack.py
        extract_terrain_tiles.py
    video2dsprite/
      SKILL.md
      references/
        pipeline.md
        prompt-rules.md
      scripts/
        flux_video.py           # FLUX 3 video API transport
        video2dsprite.py
```

## Notes

- Best results come from prompts that clearly specify view, action, and desired motion style.
- Large creatures often work better as `3x3 idle`.
- Small spells and projectiles often work better as `1x4`, `2x2`, or `2x3`.
- Layout guides are useful for fixed-frame action sheets and prop packs, but they are not always better for compact attack sheets.
- For commercial projects, prefer original characters or IP that you control.

## License

MIT. See LICENSE. Derived from [agent-sprite-forge](https://github.com/0x0funky/agent-sprite-forge) by 0x0funky.
