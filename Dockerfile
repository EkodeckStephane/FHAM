FROM python:3.13-slim

WORKDIR /workspace

COPY requirements-lock.txt pyproject.toml ./
RUN python -m pip install --no-cache-dir -r requirements-lock.txt

COPY . .
RUN python -m pip install --no-cache-dir -e . --no-deps

# External datasets (BOSSBase, BOWS2, COCO 2017) are not part of the image;
# mount them read-only at runtime and set the matching environment variables.
ENV FHAM_BOSSBASE_DIR=/data/BOSSbase \
    FHAM_BOWS2_DIR=/data/BOWS2 \
    FHAM_COCO2017_DIR=/data/coco2017/val2017

RUN python -m pytest -q

CMD ["python", "run_pipeline.py"]
