# Jarvis Cloud on Google Cloud Run

This is the Google Cloud deployment path for the existing Jarvis Cloud FastAPI service and the autonomous Instagram worker.

## Architecture

```text
Phone / Web UI
      |
      v
  Cloud Run service: jarvis-cloud
      |
      +--> OpenAI / shared memory / PC routing

Cloud Scheduler
      |
      v
Cloud Run Job: jarvis-instagram-daily
      |
      +--> audience context -> strategy -> image -> Cloudinary -> Meta publish
```

Cloud Run can build and deploy a Python/FastAPI service from source or a container. The repository includes an explicit `cloud/Dockerfile` so the service and the scheduled Instagram worker use the same image. Google documents Cloud Run jobs scheduled through Cloud Scheduler; Scheduler delivery is at-least-once, so the worker contains a recent-post guard to avoid duplicate daily publishing.

## Build the image

Set these shell variables first:

```bash
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
export REGION="asia-southeast1"
export REPO="jarvis"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/jarvis-cloud:latest"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com

gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" 2>/dev/null || true

gcloud builds submit --tag "$IMAGE" --file cloud/Dockerfile .
```

## Deploy the Jarvis Cloud service

Create a strong `JARVIS_CLOUD_SECRET` and keep it in Secret Manager or your Cloud Run environment settings. Never commit the real value.

```bash
gcloud run deploy jarvis-cloud \
  --image "$IMAGE" \
  --region "$REGION" \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars "OPENAI_API_KEY=YOUR_OPENAI_KEY,JARVIS_CLOUD_SECRET=YOUR_RANDOM_SECRET,JARVIS_CLOUD_MODEL=gpt-5-mini,JARVIS_CLOUD_DB=/tmp/jarvis_cloud.db" \
  --no-allow-unauthenticated
```

For the first test, you may temporarily use `--allow-unauthenticated` only if you understand that the app's own bearer-secret authentication still protects `/ask`, `/memory`, and heartbeat endpoints. For production, prefer platform authentication as well and give the calling server/agent an appropriate Google service identity.

The deployed service exposes:

- `/health`
- `/ask`
- `/memory`
- `/device/heartbeat`

## Deploy the autonomous Instagram job

The job uses the same image but overrides its command to run `cloud.instagram_job`.

```bash
gcloud run jobs create jarvis-instagram-daily \
  --image "$IMAGE" \
  --region "$REGION" \
  --memory 1Gi \
  --cpu 1 \
  --command python \
  --args cloud/instagram_job.py \
  --set-env-vars "OPENAI_API_KEY=YOUR_OPENAI_KEY,INSTAGRAM_ACCESS_TOKEN=YOUR_META_TOKEN,INSTAGRAM_ACCOUNT_ID=YOUR_IG_ACCOUNT_ID,CLOUDINARY_CLOUD_NAME=YOUR_CLOUDINARY_CLOUD,CLOUDINARY_API_KEY=YOUR_CLOUDINARY_KEY,CLOUDINARY_API_SECRET=YOUR_CLOUDINARY_SECRET,META_GRAPH_API_VERSION=v20.0,JARVIS_SOCIAL_MODEL=gpt-5-mini,JARVIS_INSTAGRAM_AUTOPUBLISH=false,JARVIS_INSTAGRAM_MIN_POST_INTERVAL_HOURS=20"
```

Keep `JARVIS_INSTAGRAM_AUTOPUBLISH=false` during the first end-to-end test. Change it to `true` only after a successful dry run and credential verification.

## Schedule the Instagram job

Google Cloud Scheduler can invoke Cloud Run jobs on a cron schedule. Create a dedicated service account with permission to run the job, then create the Scheduler job.

Example daily schedule at 20:30 India time:

```bash
gcloud scheduler jobs create http jarvis-instagram-daily-trigger \
  --location="$REGION" \
  --schedule="30 20 * * *" \
  --time-zone="Asia/Kolkata" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/jarvis-instagram-daily:run" \
  --http-method=POST \
  --oauth-service-account-email="YOUR_SCHEDULER_SERVICE_ACCOUNT"
```

Grant the Scheduler service account permission to invoke the Cloud Run job before creating the schedule.

## Required Instagram environment variables

```text
OPENAI_API_KEY
INSTAGRAM_ACCESS_TOKEN
INSTAGRAM_ACCOUNT_ID
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
META_GRAPH_API_VERSION=v20.0
JARVIS_SOCIAL_MODEL=gpt-5-mini
JARVIS_INSTAGRAM_AUTOPUBLISH=false   # set true only after testing
JARVIS_INSTAGRAM_MIN_POST_INTERVAL_HOURS=20
```

Optional quality controls are already supported by `instagram_autonomous.py`:

```text
JARVIS_INSTAGRAM_HIGH_QUALITY_RATE=0.15
JARVIS_INSTAGRAM_MEDIUM_QUALITY_RATE=0.65
JARVIS_INSTAGRAM_LOW_QUALITY_RATE=0.20
JARVIS_INSTAGRAM_IMAGE_SIZE=1024x1024
```

## First-run sequence

1. Deploy the service.
2. Open `https://SERVICE_URL/health` and verify `ok: true`.
3. Put the Cloud Run service URL into `web_ui/.env` as `JARVIS_CLOUD_URL`.
4. Test `/ask` through the Web UI.
5. Deploy the Instagram job with autopublish disabled.
6. Force-run the job and verify image generation + Cloudinary upload + Meta container creation.
7. Only then set `JARVIS_INSTAGRAM_AUTOPUBLISH=true` and create the daily schedule.
