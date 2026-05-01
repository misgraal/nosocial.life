# Changelog

## Unreleased - 2026-05-01

### Added

- Added resumable chunk uploads with stored upload IDs, server-side upload status checks, and byte-based progress reporting.
- Added upload speed and estimated time remaining to the upload UI.
- Added separate `Upload file` and `Upload folder` controls.
- Added media thumbnails for image and video previews through `ffmpeg`.
- Added preview support for more image formats, including HEIC, HEIF, TIFF, RAW, DNG, CR2, NEF, AVIF, WebP, SVG, BMP, and GIF.
- Added preview support for more video containers, including MKV, AVI, M2TS, MTS, WMV, FLV, VOB, MOV, WebM, MP4, MPEG, and 3GP.
- Added browser fallback actions when a media file cannot be previewed or played directly.
- Added `/health` endpoint for container health checks.
- Added Docker health checks for the FastAPI app and DLNA services.
- Added optional Jellyfin Docker Compose profile for richer media playback.
- Added optional video optimizer tool for MP4/MOV fast-start remuxing.
- Added backup script for MySQL and runtime data.
- Added admin diagnostics for storage paths, write access, DLNA media folder, temp folder, runtime directory, secure cookies, DLNA URL, and backup command.
- Added login and registration rate limiting.
- Added configurable secure cookies through `NOSOCIAL_COOKIE_SECURE`.
- Added automatic public visibility for files added to the `Movies` media folder and its subfolders.

### Changed

- Changed Linux storage layout to use a single `/mnt/storage` mount instead of split test disks.
- Changed DLNA media directory configuration to expose `/media/storage/Movies` without a video-only filter.
- Changed file content responses to use improved MIME type detection for uncommon media formats.
- Changed file sharing unlock cookies to respect the secure-cookie configuration.
- Changed deployment workflow to prepare storage directories, validate Docker Compose config, upload helper scripts, and prune old Docker images.
- Changed Docker image dependencies to include `ffmpeg` for media preview generation.
- Changed upload cleanup to run during application startup.
- Changed media-folder detection to treat `Movies` case-insensitively for upload and move operations.

### Removed

- Removed advanced search filter controls from the drive UI.

### Fixed

- Fixed Unicode filenames in `Content-Disposition` headers for preview and download responses.
- Fixed preview behavior for short videos by falling back to the first frame when the 2-second thumbnail frame is unavailable.
- Fixed stale upload state handling so resumed uploads can skip completed chunks safely.
- Fixed upload cancel handling to clear active upload IDs.

### Security

- Added same-origin protection for unsafe HTTP methods.
- Added rate limiting for login and registration attempts.
- Added secure-cookie support for HTTPS deployments.

### Operations

- The deployment package now includes `docker-compose.yml`, `minidlna.conf`, `backup.sh`, and `optimize_videos.sh`.
- Optional Jellyfin can be started with:

  ```bash
  docker compose --profile jellyfin up -d jellyfin
  ```

- A manual backup can be created with:

  ```bash
  bash backup.sh
  ```

## Repository History

This repository has no Git tags yet, so the historical changelog below is grouped by commit date and based on the local Git history for GitHub-tracked branches.

### 2026-05-01

- `805aba4` - Optimized DLNA configuration.
- `8185e59` - Fixed DLNA and folder/file service behavior.
- `ac75fb1` - Fixed DLNA deployment configuration.
- `f9db707` - Added HMS/DLNA support and phone/PWA-related assets.
- `8cd4f24` - Fixed HTTPS/CSS-related behavior.
- `0b337fc` - Fixed admin functionality.
- `fa1f0ac` - Merged remote `main`.

### 2026-04-30

- `ff28a0d` - Fixed server-side file behavior.
- `2d86992` - Added Linux/server deployment fixes.
- `824ef1f` - Updated configuration.
- `a158ea7` - Updated deployment workflow.
- `55ea84d` - Added chunk upload changes.
- `e95cb0f` - Updated local environment helper.
- `3d06d21` - Added deployment/config test changes.
- `c516526` - Added the major file/folder system update, including file services, folders, file viewer, sharing, and related web routes.

### 2026-03-26

- `109d968` - Updated deployment workflow.
- `b9bf9c0` - Updated Dockerfile deployment setup.
- `1f2a56a` - Replaced Docker workflow with deploy workflow and added server Docker Compose files.
- `ec89aa5` - Added initial files UI/database changes.

### 2026-03-25

- `5a364d1` - Added folder system 1.0.
- `e1d06c8` - Updated app UI and route behavior.
- `d4ef665` - Updated app/folder service behavior and local editor settings.

### 2026-03-19

- `60b7a54` - Added app 0.2 changes, folder hash generation, and folder table updates.

### 2026-03-17

- `419f0e0` - Merged remote `main`.
- `5d2bdf0` - Updated admin database logic.
- `1b2a674` - Added app startup 0.1 flow.
- `1c0a315` - Updated app configuration.

### 2026-02-24

- `6504c1e` - Updated Docker workflow on the `app_main` branch.
- `d22eafe` - Added user root folder checks on the `app_main` branch.

### 2026-02-12

- `f61223e` - Updated system requirements documentation.

### 2026-02-10

- `c63eac3` - Added `config.py`.
- `603b765` - Updated Docker workflow.
- `852cd93` - Updated Docker workflow.

### 2026-02-05

- `c84a312` - Updated Docker workflow.
- `d434013` - Added Dockerfile and Docker build workflow.
- `a31597d` - Added SQL table structure for files and folders.

### 2026-01-29

- `578bcde` - Updated README.
- `66681f5` - Updated README.
- `eb1fd97` - Updated README.
- `222bab1` - Updated README.

### 2026-01-27

- `17c807a` - Added usernames, roles, admin database/service logic, and admin panel updates.

### 2026-01-15

- `e636c0c` - Added first admin panel frontend.
- `f7b3b12` - Updated work plan documentation.

### 2026-01-14

- `a74f7d3` - Added project documentation and README.
- `4652615` - Updated login behavior.
- `c279966` - Added session support.
- `46be1eb` - Removed `.DS_Store` files.
- `ad4abb9` - Removed Python cache files.
- `6b88558` - Renamed SQL folder structure.
- `65a454e` - Removed test file.
- `8cc0c91` - Completed login/register system with password hashing.

### 2026-01-13

- `16e95f2` - Added first registration service/database flow.

### 2026-01-10

- `27a80b3` - Added first app pages, login/register routes, database module, and frontend scripts.
- `da1dd11` - Added requirements and initial project cleanup.
- `6374a95` - Created the project base.
