#!/usr/bin/env bash
# Встановлюємо залежності Python
pip install -r requirements.txt

# Встановлюємо ffmpeg через статичний бінарник, якщо apt-get не працює
mkdir -p bin
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar xJ -C bin --strip-components 1
export PATH=$PATH:$(pwd)/bin
