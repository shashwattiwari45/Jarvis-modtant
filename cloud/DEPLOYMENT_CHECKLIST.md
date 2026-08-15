# Cloud Run deployment checklist

- [ ] Create/select Google Cloud project and enable billing.
- [ ] Enable Cloud Run, Artifact Registry, and Cloud Scheduler APIs.
- [ ] Create the `jarvis` Artifact Registry repository.
- [ ] Build and push the image from `cloud/Dockerfile`.
- [ ] Deploy `jarvis-cloud`.
- [ ] Set `JARVIS_CLOUD_SECRET` and `OPENAI_API_KEY` as runtime secrets; never commit values.
- [ ] Verify `/health`.
- [ ] Set `JARVIS_CLOUD_URL` in `web_ui/.env` to the Cloud Run URL.
- [ ] Verify UI chat through Cloud.
- [ ] Configure Meta/Instagram + Cloudinary credentials for the job.
- [ ] Run `jarvis-instagram-daily` once with `JARVIS_INSTAGRAM_AUTOPUBLISH=false`.
- [ ] Confirm image generation and public media upload succeed.
- [ ] Confirm Meta media container creation succeeds.
- [ ] Enable autopublish only after the dry run passes.
- [ ] Create the Cloud Scheduler trigger in `Asia/Kolkata`.
- [ ] Test one scheduled execution and inspect Cloud Run job logs.
