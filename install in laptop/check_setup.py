import subprocess
import sys


def heading(text):
    print("\n" + text)
    print("-" * len(text))


print("Neural Rover setup check")
print("Python:", sys.version.split()[0])

heading("NVIDIA GPU")
try:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    print(result.stdout.strip())
except Exception as error:
    print("nvidia-smi was not available:", error)

heading("Python packages")
try:
    import cv2
    import insightface
    import numpy
    import onnxruntime as ort

    print("OpenCV:", cv2.__version__)
    print("InsightFace:", getattr(insightface, "__version__", "installed"))
    print("NumPy:", numpy.__version__)
    print("ONNX Runtime:", ort.__version__)

    if hasattr(ort, "preload_dlls"):
        try:
            ort.preload_dlls(directory="")
        except Exception as error:
            print("CUDA DLL preload warning:", error)

    providers = ort.get_available_providers()
    print("Execution providers:", providers)

    if "CUDAExecutionProvider" in providers:
        print("\nPASS: buffalo_l can use the NVIDIA GPU.")
    else:
        print("\nWARNING: CUDAExecutionProvider is missing.")
        print("Recognition can run on CPU, but it will be slower.")

except Exception as error:
    print("\nFAIL:", error)
    print("Run 01_INSTALL_GPU.bat again.")
    raise SystemExit(1)
