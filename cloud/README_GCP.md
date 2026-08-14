# Google Cloud deployment files

Use `GCP_CLOUD_RUN.md` for the exact Cloud Run + Cloud Scheduler setup.

The repository now contains:

- `Dockerfile` for the FastAPI Cloud Run service and shared Instagram job image.
- `instagram_job.py` for scheduled autonomous Instagram execution.
- `.env.gcp.example` containing the required service/job configuration names only.
- `.dockerignore` to keep secrets and frontend build artifacts out of the image.

Do not commit real API keys, Meta tokens, or Cloudinary secrets.
