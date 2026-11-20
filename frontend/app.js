const $ = (selector) => document.querySelector(selector);
let rtcClient = null;
let localAudioTrack = null;
let activeAgentSessionId = null;

const categoryLabels = {
  garbage: 'Garbage', pothole: 'Pothole / road', streetlight: 'Streetlight',
  drainage: 'Drainage', water_leakage: 'Water leakage', other: 'Other issue'
};

function setVoiceStatus(message) {
  $('#voiceStatus').textContent = message;
}

async function loadReports() {
  const container = $('#reportsList');
  try {
    const response = await fetch('/api/complaints?limit=30');
    if (!response.ok) throw new Error('Could not load reports');
    const reports = await response.json();
    if (!reports.length) {
      container.innerHTML = '<div class="empty-state">No reports yet. Be the first to raise an issue in your neighbourhood.</div>';
      return;
    }
    container.innerHTML = reports.map((report) => `
      <article class="report-item">
        <div class="report-item-top"><span class="report-category">${escapeHtml(categoryLabels[report.category] || report.category)}</span><span class="report-status">${escapeHtml(report.status.replaceAll('_',' '))}</span></div>
        <p class="report-description">${escapeHtml(report.description)}</p>
        <div class="report-meta"><span>${escapeHtml(report.area)}${report.landmark ? ` · ${escapeHtml(report.landmark)}` : ''}</span><span>${escapeHtml(report.complaint_id)}</span></div>
      </article>`).join('');
  } catch (error) {
    container.innerHTML = '<div class="empty-state">Could not load reports. Check that the backend is running.</div>';
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

async function stopVoiceSession() {
  if (localAudioTrack) {
    localAudioTrack.stop();
    localAudioTrack.close();
    localAudioTrack = null;
  }
  if (rtcClient) {
    await rtcClient.leave();
    rtcClient = null;
  }
  if (activeAgentSessionId) {
    try { await fetch(`/api/voice/session/${encodeURIComponent(activeAgentSessionId)}/stop`, { method: 'POST' }); } catch (_) { /* idle timeout is the fallback */ }
  }
  activeAgentSessionId = null;
  $('#voiceButton').classList.remove('active');
  $('#voiceButton').setAttribute('aria-label', 'Start voice assistant');
  $('#voiceAction').textContent = 'Start a conversation ↗';
  setVoiceStatus('Call ended. You can start another conversation anytime.');
}

async function startVoiceSession() {
  const button = $('#voiceAction');
  button.disabled = true;
  button.textContent = 'Connecting…';
  setVoiceStatus('Connecting to NammaResolve. Please allow microphone access.');
  try {
    const response = await fetch('/api/voice/session', { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not start the voice session');
    if (!window.AgoraRTC) throw new Error('Agora Web SDK did not load. Check your internet connection.');

    rtcClient = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });
    rtcClient.on('user-published', async (user, mediaType) => {
      await rtcClient.subscribe(user, mediaType);
      if (mediaType === 'audio') user.audioTrack.play();
    });
    rtcClient.on('user-left', () => setVoiceStatus('The assistant left the call.'));

    await rtcClient.join(data.app_id, data.channel, data.token, data.uid);
    localAudioTrack = await AgoraRTC.createMicrophoneAudioTrack();
    await rtcClient.publish([localAudioTrack]);
    activeAgentSessionId = data.agent_session_id;
    $('#voiceButton').classList.add('active');
    $('#voiceButton').setAttribute('aria-label', 'End voice assistant session');
    button.textContent = 'End conversation';
    setVoiceStatus("You’re connected. Go ahead and describe the issue.");
  } catch (error) {
    setVoiceStatus(error.message || 'Something went wrong while connecting.');
    button.textContent = 'Try again ↗';
  } finally {
    button.disabled = false;
  }
}

$('#voiceAction').addEventListener('click', async () => {
  if (rtcClient) {
    await stopVoiceSession();
    return;
  }
  await startVoiceSession();
});
$('#voiceButton').addEventListener('click', async () => {
  if (rtcClient) await stopVoiceSession();
  else await startVoiceSession();
});

$('#complaintForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#formMessage');
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  if (!payload.landmark) delete payload.landmark;
  submit.disabled = true;
  message.classList.remove('error');
  message.textContent = 'Submitting your report…';
  try {
    const response = await fetch('/api/complaints', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || 'Unable to submit report');
    message.textContent = `Report created. Your NammaResolve reference is ${data.complaint_id}. This is not an official BBMP ticket.`;
    event.currentTarget.reset();
    await loadReports();
  } catch (error) {
    message.classList.add('error');
    message.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

$('#refreshReports').addEventListener('click', loadReports);
document.querySelectorAll('.issue-chip').forEach((chip) => chip.addEventListener('click', () => {
  $('#category').value = chip.dataset.category;
  document.querySelectorAll('.issue-chip').forEach((item) => item.classList.remove('selected'));
  chip.classList.add('selected');
  $('#report').scrollIntoView({ behavior: 'smooth', block: 'center' });
}));

loadReports();
