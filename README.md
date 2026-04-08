---
title: Chota Dhobi
emoji: 🧺
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# Chota Dhobi - Laundry Management System

This repository contains the backend and frontend for the Chota Dhobi laundry management system.

## Hugging Face Hosting Instructions

This application is configured to run automatically as a **Docker Space** on Hugging Face Spaces.

### How to deploy to Hugging Face Spaces:

1. Create a new Space on [Hugging Face](https://huggingface.co/spaces).
2. Choose **Docker** as the Space SDK and choose **Blank**.
3. Push the contents of this repository to the remote repository provided by Hugging Face.
   Alternatively, you can just connect your GitHub repository and Hugging Face will automatically build it.
4. Set up your **Space Secrets** on Hugging Face (Settings -> Secrets) for your application variables:
   - `SECRET_KEY` (Used for Flask sessions and auth, set to a random secure string)
5. Hugging Face Spaces will automatically build the `Dockerfile`, install the dependencies via `requirements.txt`, and start your application on port 7860 using Gunicorn.

Note: This app uses a local SQLite database file at `data/student.db` (configurable via `SQLITE_DIR`). On hosting platforms, the container can reset, so data persists only if you attach a disk/volume.

## Render Deployment

This repo includes a `render.yaml` blueprint for Render.

Key settings:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Persistent disk: mounted at `/opt/render/project/src/data` (used by `SQLITE_DIR`)
  (requires a Render plan that supports disks)

If you deploy via the Render dashboard manually, ensure:
- `SECRET_KEY` is set
- `SQLITE_DIR` is set to the disk mount path
