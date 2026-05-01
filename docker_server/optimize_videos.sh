#!/bin/sh
set -eu

MEDIA_DIR="${MEDIA_DIR:-/media/storage/Movies}"

if [ ! -d "$MEDIA_DIR" ]; then
  echo "Media directory does not exist: $MEDIA_DIR" >&2
  exit 1
fi

find "$MEDIA_DIR" -type f \( -iname '*.mp4' -o -iname '*.m4v' -o -iname '*.mov' \) -print | while IFS= read -r file; do
  tmp="${file}.faststart.tmp"
  backup="${file}.pre-faststart"

  if [ -f "$backup" ]; then
    echo "Skipping already optimized candidate: $file"
    continue
  fi

  echo "Optimizing: $file"
  ffmpeg -hide_banner -loglevel error -y -i "$file" -c copy -movflags +faststart "$tmp"
  mv "$file" "$backup"
  mv "$tmp" "$file"
  rm -f "$backup"
done

echo "Video optimization completed."
