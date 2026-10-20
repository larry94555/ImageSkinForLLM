# The app as one container image, for a hosted HTTPS site (roadmap R32). It is run behind Caddy,
# which adds HTTPS and the password: see deploy/README.md. Builds for x86-64 and for ARM (Oracle
# Cloud's free Ampere machines).
FROM ubuntu:24.04

# Python 3.12 (Kokoro and MediaPipe need 3.11 or 3.12). ffmpeg converts the recordings and
# writes the videos, git fetches LivePortrait's code on the first prepare, and MediaPipe needs
# libegl1 and libgles2 on a Linux server.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv ca-certificates ffmpeg git libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*
RUN python3.12 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
# The CPU-only PyTorch and torchaudio: the server has no GPU, and they are far smaller. The
# versions the cloned voice was tested with (clone-requirements.txt). torchaudio must come from
# the same index: PyPI's Linux build needs CUDA (libcudart.so.13), so Chatterbox couldn't load it.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch==2.14.1 torchaudio==2.11.0 --index-url "$TORCH_INDEX"

COPY pyproject.toml README.md LICENSE clone-requirements.txt ./
COPY src ./src
# The app with every extra and what Chatterbox (the person's own voice) needs, resolved together
# so the versions agree, then Chatterbox itself without its old pins, as in the README's "Your
# own voice". MediaPipe also installs the full OpenCV, which must stay on 4.x as the app's does.
# Kokoro's English model is installed here too: Kokoro would install it on first use, and the app
# can't write to the installed packages.
RUN pip install --no-cache-dir --retries 10 ".[voice,photoreal,faces,heic]" \
        -r clone-requirements.txt "opencv-contrib-python>=4.8,<5" \
    && pip install --no-cache-dir --no-deps chatterbox-tts==0.1.7 \
    && python -m spacy download en_core_web_sm

COPY deploy/config.toml /etc/imageskin/config.toml
# Ubuntu's image already has a user 1000 (ubuntu); the app runs as it, not as root.
RUN mkdir /data && chown ubuntu /data
USER ubuntu
# Uploads, the prepared face, the settings with any API keys, and the downloaded models are
# all kept in /data, a volume, so they outlive a new image.
ENV IMAGESKIN_HOME=/data HF_HOME=/data/huggingface
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["imageskin", "--config", "/etc/imageskin/config.toml", "serve"]
