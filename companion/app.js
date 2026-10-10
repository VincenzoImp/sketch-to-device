'use strict';
const $ = selector => document.querySelector(selector);
let token = sessionStorage.getItem('workspace-token') || '';
let attachments = [], recorder = null, recordingTimer = null, captureStream = null, working = false;
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has('token')) {
  token = fragment.get('token');
  sessionStorage.setItem('workspace-token', token);
  history.replaceState(null, '', location.pathname);
}
function showError(message) { $('#error').textContent = message; $('#error').hidden = false; }
const errors = {
  authentication_required:'Open your private workspace link to connect.',
  generation_busy:'An app is already being built. Please wait for it to finish.',
  generation_stalled:'The app builder repeated the same failed result. Your current app is unchanged. Try describing what should happen differently.',
  input_required:'Describe your app or add a recording.',
  unsupported_request:'This idea needs features that are not available on your device yet. Retrying the same request will not add them. Your current app is still available.',
  unsupported_or_oversized_media:'Choose a supported image or recording up to 20 MiB.',
  invalid_body_size:'This upload is empty or too large. Choose a file up to 20 MiB.',
  incomplete_upload:'The upload was interrupted. Check your connection and try again.',
  upload_timeout:'The upload stopped responding. Check your connection or choose a smaller file, then try again.',
  combined_media_too_large:'Keep all attachments together within 32 MiB.',
  media_conversion_unavailable:'Audio conversion is not ready on the server yet.',
  service_error:'The service could not complete this step. Please try again.',
  request_conflict:'This request changed. Submit it as a new app.',
  provider_response:'Gemini could not finish building this app. Your current app is unchanged. You can try again.',
  provider_request:'Gemini could not process this request. Your current app is unchanged. You can try again.',
  provider_quota:'The app builder has reached its usage limit. Wait before trying again.',
  provider_auth:'The app builder needs its connection settings checked before trying again.',
  configuration:'The app builder needs its connection settings checked before trying again.',
  network:'The app builder could not be reached. Check the internet connection before trying again.',
  provider_transport:'The connection to the app builder was interrupted. Check the internet connection before trying again.',
  deadline:'The app builder reached its time limit. Your current app is unchanged. You can try again.',
  speech:'The recording could not be understood. Try a clear, short English voice note.',
  media:'This attachment could not be read. Try another image or a short recording.',
  media_limit:'Use up to 3 files, 20 MiB each and 32 MiB total. Audio can be 60 seconds; video 30 seconds.',
  media_size:'Choose a file up to 20 MiB. If a photo still fails, export a smaller JPEG.',
  media_dimensions:'Choose a photo up to 40 megapixels, with neither side larger than 12,000 pixels.',
  media_duration:'Use audio up to 60 seconds or video up to 30 seconds. Longer recordings are not cut automatically.',
  media_timeout:'This attachment took too long to process. Try a smaller photo or a shorter recording.',
  media_tools:'Media processing is unavailable on the server. Try a text request while it is checked.',
  input:'Describe your app or add a supported image or recording.',
  repair_limit:'The app did not pass its checks. Try a simpler description.',
  tool_protocol:'The app did not pass its checks. Try a simpler description.'
};
function failureMessage(code, reason) {
  if (reason === 'token_budget_exhausted') return 'The app builder reached its work limit. Your current app is unchanged. You can try again.';
  return typeof errors[code] === 'string' ? errors[code] : 'The app could not be completed. Your current app is unchanged. You can try again.';
}
async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers:{Authorization:`Bearer ${token}`, ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof errors[data.error] === 'string' ? errors[data.error] : 'The service could not complete this step. Please try again.');
    error.status = response.status; throw error;
  }
  return data;
}
async function connect() {
  $('#connect').hidden = Boolean(token); $('#workspace').hidden = !token;
  if (!token) return;
  try { const data = await request('/api/session'); updateDevice(data.device_online); }
  catch (error) { $('#connect').hidden = false; $('#workspace').hidden = true; showError(error.message); return; }
  if (sessionStorage.getItem('pending-request') || sessionStorage.getItem('last-job')) await recover();
}
function updateDevice(online) {
  $('#device-status').textContent = online ? 'Connected · ready to receive' : 'Paired · waiting for connection';
  $('#device-dot').classList.toggle('online', online);
}
$('#connect-form').addEventListener('submit', event => {
  event.preventDefault(); token = $('#access-token').value.trim(); sessionStorage.setItem('workspace-token', token); $('#error').hidden = true; connect();
});
function renderFiles() {
  $('#file-list').replaceChildren();
  attachments.forEach((file, index) => {
    const row = document.createElement('li'), name = document.createElement('span'), remove = document.createElement('button');
    name.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MiB`;
    remove.textContent = 'Remove'; remove.type = 'button'; remove.disabled = working;
    remove.onclick = () => { attachments.splice(index, 1); renderFiles(); };
    row.append(name, remove); $('#file-list').append(row);
  });
}
function addFiles(files) {
  for (const file of files) {
    if (attachments.length >= 3) { showError('Choose up to 3 attachments.'); break; }
    if (!file.size || file.size > 20 * 1024 * 1024) { showError('Each attachment must contain data and be no larger than 20 MiB.'); continue; }
    if (attachments.reduce((total, item) => total + item.size, 0) + file.size > 32 * 1024 * 1024) { showError('Keep all attachments together within 32 MiB.'); continue; }
    attachments.push(file);
  }
  renderFiles();
}
$('#files').onchange = event => { addFiles([...event.target.files]); event.target.value = ''; };
$('#record').onclick = async () => {
  if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { showError('Voice recording needs HTTPS in this browser. You can add a recording from your phone instead.'); return; }
  if (attachments.length >= 3) { showError('Remove an attachment before recording.'); return; }
  try {
    captureStream = await navigator.mediaDevices.getUserMedia({audio:true});
    const mimeType = ['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
    recorder = new MediaRecorder(captureStream, mimeType ? {mimeType} : undefined);
    const chunks = []; recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      clearTimeout(recordingTimer); captureStream.getTracks().forEach(track => track.stop());
      const mime = recorder.mimeType.split(';')[0];
      addFiles([new File(chunks, `My idea.${mime.includes('mp4') ? 'm4a' : 'webm'}`, {type:mime})]);
      recorder = null; $('#record').textContent = '● Record voice'; $('#generate').disabled = false;
    };
    recorder.start(); $('#record').textContent = '■ Stop recording'; $('#generate').disabled = true;
    recordingTimer = setTimeout(() => { if (recorder?.state === 'recording') recorder.stop(); }, 60000);
  } catch (_) { if (captureStream) captureStream.getTracks().forEach(track => track.stop()); showError('Microphone access was unavailable. Add a recording or type your idea.'); }
};
function progress(stage, detail, deployment, diagnostics) {
  const titles = {preparing:'Preparing your idea',uploading:'Sending your sketch',transcribing:'Listening to your idea',understanding:'Reading your sketch',generating:'Building your app',repairing:'Improving your app',validating:'Checking the app',simulating:'Trying the app',ready:'On its way to your device',active:'Your idea is alive.',failed:'Your app could not be created',superseded:'A newer idea is being built'};
  const unsupported = stage === 'failed' && detail === 'unsupported_request';
  $('#progress').hidden = false; $('#progress-title').textContent = unsupported ? 'This idea is not supported yet' : titles[stage] || 'Working on your app';
  $('#progress-detail').textContent = stage === 'failed' ? failureMessage(detail, diagnostics?.reason) : detail || '';
  $('#progress-label').textContent = unsupported ? 'NOT SUPPORTED YET' : stage === 'failed' ? 'APP NOT CREATED' : stage === 'active' ? 'RUNNING ON YOUR DEVICE' : 'MAKING YOUR APP';
  const phase = ['ready','active'].includes(stage) ? 2 : ['generating','repairing','validating','simulating'].includes(stage) ? 1 : 0;
  [...$('#steps').children].forEach((step, index) => { step.classList.toggle('done', index < phase || stage === 'active'); step.classList.toggle('current', index === phase && !['active','failed','superseded'].includes(stage)); });
  $('#identity').textContent = deployment ? `${deployment.manifest.app_id} · v${deployment.manifest.version} · ${deployment.manifest.sha256.slice(0,12)}` : '';
}
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
function requestId() { return [...crypto.getRandomValues(new Uint8Array(16))].map(byte => byte.toString(16).padStart(2,'0')).join(''); }
function setWorking(value) {
  working = value; $('#generate').disabled = value; $('#files').disabled = value; $('#record').disabled = value;
  const pending = sessionStorage.getItem('pending-request') || sessionStorage.getItem('last-job');
  $('#generate').textContent = !value && pending ? 'Resume request ↗' : 'Generate and install ↗'; renderFiles();
}
async function acceptPending() {
  const frozen = sessionStorage.getItem('pending-request');
  if (!frozen) return;
  const result = await request('/api/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:frozen});
  sessionStorage.setItem('last-job', result.job_id); sessionStorage.removeItem('pending-request');
}
function reportFailure(error) {
  if (error.status >= 400 && error.status < 500 && error.status !== 401) {
    sessionStorage.removeItem('pending-request');
  }
  showError(error.message);
}
async function recover() {
  if (working) return;
  setWorking(true); $('#error').hidden = true;
  try {
    progress('preparing', 'Reconnecting to your saved request.');
    await acceptPending();
    const identifier = sessionStorage.getItem('last-job');
    if (identifier) await watch(identifier);
  } catch (error) { reportFailure(error); }
  finally { setWorking(false); }
}
$('#create-form').addEventListener('submit', async event => {
  event.preventDefault(); if (working) return;
  if (sessionStorage.getItem('pending-request') || sessionStorage.getItem('last-job')) { await recover(); return; }
  const prompt = $('#prompt').value.trim(), files = [...attachments];
  if (!prompt && !files.length) { showError('Describe your app or add a recording.'); return; }
  setWorking(true); $('#error').hidden = true;
  try {
    progress('uploading', files.length ? 'Uploading the material for this app.' : 'Freezing your request.');
    const uploads = [];
    for (const file of files) {
      const result = await request('/api/uploads', {method:'POST',headers:{'Content-Type':file.type || 'application/octet-stream'},body:file});
      uploads.push(result.upload_id);
    }
    sessionStorage.setItem('pending-request', JSON.stringify({prompt,uploads,request_id:requestId()}));
    await acceptPending();
    await watch(sessionStorage.getItem('last-job'));
  } catch (error) { reportFailure(error); }
  finally { setWorking(false); }
});
async function watch(identifier) {
  const deadline = Date.now() + 15 * 60 * 1000;
  let awaitingDevice = false;
  while (Date.now() < deadline) {
    const job = await request(`/api/jobs/${encodeURIComponent(identifier)}`);
    awaitingDevice = job.stage === 'ready';
    progress(job.stage, job.detail, job.deployment, job.diagnostics); updateDevice(job.device_online);
    if (['active','failed','superseded'].includes(job.stage)) { sessionStorage.removeItem('last-job'); return; }
    await pause(1500);
  }
  showError(awaitingDevice
    ? 'Your app is waiting for the device. Check its connection, then tap Resume request to see its status.'
    : 'This request is still in progress. Tap Resume request to reconnect to it.');
}
connect();
setInterval(async () => { if (token && !working) { try { updateDevice((await request('/api/session')).device_online); } catch (_) {} } }, 5000);
