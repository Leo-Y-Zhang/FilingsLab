"""
setup_kronos.py — One-time Kronos AI model setup for FilingsLab
===========================================================
Run once from the project root before starting FilingsLab:

    python setup_kronos.py

What it does:
  1. Clones the Kronos repo (MIT licence) into  backend/kronos_lib/
  2. Verifies PyTorch is installed (installs CPU build if missing)
  3. Confirms all Kronos dependencies are present

After running this:
  - Rebuild Docker:  docker compose up --build
  - Model weights (~50 MB) auto-download from HuggingFace on first forecast.

Hardware note:
  - GPU (8 GB+ VRAM) → ~3 s per forecast
  - CPU-only         → ~30–120 s per forecast (still works)
  - For CUDA GPU support install the matching torch wheel:
    https://pytorch.org/get-started/locally/
"""
import subprocess
import sys
from pathlib import Path

KRONOS_REPO = "https://github.com/shiyu-coder/Kronos.git"
DEST = Path(__file__).parent / "backend" / "kronos_lib"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"  › {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kw)


def main() -> None:
    print("=" * 62)
    print("  FilingsLab — Kronos AI Forecast Setup")
    print("=" * 62)

    # ── Step 1: clone ──────────────────────────────────────────────
    if DEST.exists():
        print(f"\n[1/3] ✓ Kronos already present at {DEST}")
        print("      Delete backend/kronos_lib/ and re-run to refresh.")
    else:
        print(f"\n[1/3] Cloning Kronos (MIT) → backend/kronos_lib/ …")
        try:
            run(["git", "clone", "--depth", "1", KRONOS_REPO, str(DEST)])
            print("      ✓ Clone complete.")
        except subprocess.CalledProcessError:
            print("\n  ERROR: git clone failed.")
            print("  Make sure git is installed and you have internet access.")
            sys.exit(1)

    # ── Step 2: verify torch ───────────────────────────────────────
    print("\n[2/3] Checking PyTorch …")
    try:
        import torch
        print(f"      ✓ torch {torch.__version__}")
        if torch.cuda.is_available():
            print(f"      ✓ GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            print("      ⚠  No GPU detected — forecasts will run on CPU.")
            print("         For CUDA: https://pytorch.org/get-started/locally/")
    except ImportError:
        print("      Installing CPU-only PyTorch …")
        run([sys.executable, "-m", "pip", "install", "torch",
             "--index-url", "https://download.pytorch.org/whl/cpu"])

    # ── Step 3: other Kronos deps ──────────────────────────────────
    print("\n[3/3] Checking Kronos dependencies …")
    deps = ["einops", "huggingface_hub", "safetensors", "tqdm", "yfinance"]
    missing = []
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)

    if missing:
        print(f"      Installing: {', '.join(missing)}")
        run([sys.executable, "-m", "pip", "install"] + missing)
    else:
        print("      ✓ All dependencies present.")

    print("\n" + "=" * 62)
    print("  Setup complete!")
    print()
    print("  Next steps:")
    print("    1.  docker compose up --build")
    print("    2.  Open http://localhost → Forecast page")
    print("    3.  Model weights (~50 MB) download on first forecast click.")
    print("=" * 62)


if __name__ == "__main__":
    main()
