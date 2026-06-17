# skill.tee.v1 — example skill

Wedding photo style transfer demo. Illustrates the `skill.tee.v1` package format and the `skill_runner.py` reference runner.

## Files

| File | Purpose |
|---|---|
| `johnny_wedding.skill.json` | Main spec — targets Chutes ACI (attested confidential inference) |
| `johnny_wedding_fal.skill.json` | Same pipeline, fal.ai backend |
| `johnny_wedding_pil.skill.json` | Same pipeline, local PIL (no API key needed) |
| `skill_runner.py` | Runner — dispatches ffmpeg / fal / chutes-aci / pil-style steps |
| `test_skill_runner.py` | 7 tests (mock inference, no API key required) |
| `dev_assets/` | Local stand-ins for `/tee/skill/` paths in prod |

## Run tests

```
pip install pytest pillow numpy
pytest test_skill_runner.py -v
```

## Run end-to-end (PIL, no API key)

```
python skill_runner.py johnny_wedding_pil.skill.json input.jpg output.jpg \
  --tee-root ./dev_assets/
```

## Run end-to-end (fal.ai)

```
FAL_KEY=your-key python skill_runner.py johnny_wedding_fal.skill.json input.jpg output.jpg \
  --tee-root ./dev_assets/
```

## Dev vs prod

`--tee-root ./dev_assets/` remaps all `/tee/skill/` paths to local dev assets. In prod (dstack TDX), the same skill.json runs without `--tee-root`; the network policy in docker-compose enforces `allowNet` at the kernel level, bound in RTMR3.
