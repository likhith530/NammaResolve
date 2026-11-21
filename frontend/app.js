const $ = (selector) => document.querySelector(selector);
let rtcClient = null;
let localAudioTrack = null;
let activeAgentSessionId = null;
let transcriptPoll = null;
let renderedTranscriptIds = new Set();
let selectedVoiceLanguage = 'en-US';

const categoryLabels = {
  garbage: 'Garbage', pothole: 'Pothole / road', streetlight: 'Streetlight',
  drainage: 'Drainage', water_leakage: 'Water leakage', other: 'Other issue'
};

function setVoiceStatus(message) {
  $('#voiceStatus').textContent = message;
}

async function loadPocs() {
  const container = $('#pocList');
  try {
    const response = await fetch('/api/pocs');
    if (!response.ok) throw new Error('Could not load POCs');
    const pocs = await response.json();
    container.innerHTML = pocs.map((poc) => `
      <article class="poc-item">
        <div><strong>${escapeHtml(poc.area)}</strong><span>${escapeHtml(poc.constituency)}</span></div>
        <p><b>MLA:</b> ${escapeHtml(poc.mla_name)}<br><span>${escapeHtml(poc.mla_email)}</span></p>
        <p><b>POC:</b> ${escapeHtml(poc.poc_name)}<br><span>${escapeHtml(poc.poc_email)}</span></p>
      </article>`).join('');
  } catch (error) {
    container.innerHTML = '<div class="empty-state">Could not load demo POCs.</div>';
  }
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
      <article class="report-item report-item-clickable" data-report-id="${escapeHtml(report.complaint_id)}" tabindex="0" role="button">
        <div class="report-item-top"><span class="report-category">${escapeHtml(categoryLabels[report.category] || report.category)}</span><span class="report-status">${escapeHtml(report.status.replaceAll('_',' '))}</span></div>
        <p class="report-description">${escapeHtml(report.description)}</p>
        <div class="report-meta"><span>${escapeHtml(report.area)}${report.landmark ? ` · ${escapeHtml(report.landmark)}` : ''}</span><span>${escapeHtml(report.complaint_id)}</span></div>
      </article>`).join('');
    document.querySelectorAll('.report-item-clickable').forEach((item) => {
      const open = () => openReportDetail(item.dataset.reportId);
      item.addEventListener('click', open);
      item.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') open();
      });
    });
  } catch (error) {
    container.innerHTML = '<div class="empty-state">Could not load reports. Check that the backend is running.</div>';
  }
}

async function openReportDetail(complaintId) {
  const modal = $('#reportModal');
  const content = $('#reportModalContent');
  content.innerHTML = '<div class="empty-state">Loading report…</div>';
  modal.hidden = false;
  try {
    const response = await fetch(`/api/complaints/${encodeURIComponent(complaintId)}`);
    if (!response.ok) throw new Error('Report not found');
    const report = await response.json();
    content.innerHTML = `
      <div class="report-detail-heading">
        <div><span class="section-kicker">NAMMARESOLVE REPORT</span><h2>${escapeHtml(report.complaint_id)}</h2></div>
        <button type="button" id="closeReportModal" class="refresh-button" aria-label="Close report">×</button>
      </div>
      <dl class="report-detail-grid">
        <div><dt>Category</dt><dd>${escapeHtml(categoryLabels[report.category] || report.category)}</dd></div>
        <div><dt>Status</dt><dd>${escapeHtml(report.status)}</dd></div>
        <div><dt>Area</dt><dd>${escapeHtml(report.area)}</dd></div>
        <div><dt>Landmark</dt><dd>${escapeHtml(report.landmark || 'Not provided')}</dd></div>
      </dl>
      <p class="report-detail-description">${escapeHtml(report.description)}</p>
      <div class="proof-section">
        <h3>Proof</h3>
        ${report.proof_url
          ? `<a class="proof-preview" href="${escapeHtml(report.proof_url)}" target="_blank" rel="noopener">View uploaded proof</a>`
          : '<p class="panel-subtitle">No proof has been added.</p>'}
        <input id="proofInput" type="file" accept="image/*" />
        <button type="button" id="uploadProofButton" class="primary-button">Add proof</button>
      </div>
      <div id="emailPreview" class="email-preview"></div>
      <div class="report-detail-actions">
        <button type="button" id="previewEmailButton" class="primary-button email-preview-button">Preview email</button>
        <a class="primary-button report-download" href="/api/complaints/${encodeURIComponent(report.complaint_id)}/pdf">Download PDF <span>↓</span></a>
      </div>`;

    $('#closeReportModal').addEventListener('click', () => { modal.hidden = true; });
    $('#previewEmailButton').addEventListener('click', async () => {
      const response = await fetch(`/api/complaints/${encodeURIComponent(report.complaint_id)}/email-preview`);
      if (!response.ok) return;
      const preview = await response.json();
      $('#emailPreview').innerHTML = `
        <h3>Email demo preview <span class="demo-label">No email sent</span></h3>
        <p><b>To:</b> ${escapeHtml(preview.to.join(', '))}</p>
        <p><b>Subject:</b> ${escapeHtml(preview.subject)}</p>
        <pre>${escapeHtml(preview.body)}</pre>`;
    });
    $('#uploadProofButton').addEventListener('click', async () => {
      const file = $('#proofInput').files[0];
      if (!file) return;
      const form = new FormData();
      form.append('proof', file);
      const upload = await fetch(`/api/complaints/${encodeURIComponent(report.complaint_id)}/proof`, {
        method: 'POST', body: form
      });
      if (!upload.ok) {
        alert('Could not upload proof');
        return;
      }
      await openReportDetail(report.complaint_id);
      await loadReports();
    });
  } catch (error) {
    content.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

async function appendTranscript(speaker, text, isFinal = true) {
  if (!activeAgentSessionId || !text.trim()) return;
  try {
    await fetch(`/api/voice/session/${encodeURIComponent(activeAgentSessionId)}/transcript`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({speaker, text: text.trim(), is_final: isFinal})
    });
  } catch (error) {
    console.warn('[TRANSCRIPT] Could not save entry', error);
  }
}

function renderTranscript(entries) {
  const captions = $('#liveCaptions');
  if (!entries.length) {
    captions.innerHTML = '<p class="caption-placeholder">Captions will appear here during the conversation.</p>';
    return;
  }
  captions.innerHTML = entries.map((entry) => `
    <p class="caption-${entry.speaker}"><strong>${escapeHtml(entry.speaker)}</strong>${escapeHtml(entry.text)}</p>
  `).join('');
  captions.scrollTop = captions.scrollHeight;
}

async function refreshTranscript() {
  if (!activeAgentSessionId) return;
  try {
    const response = await fetch(`/api/voice/session/${encodeURIComponent(activeAgentSessionId)}/transcript`);
    if (!response.ok) return;
    const entries = await response.json();
    renderTranscript(entries);
  } catch (error) {
    console.warn('[TRANSCRIPT] Could not load entries', error);
  }
}

async function stopVoiceSession() {
  if (transcriptPoll) {
    clearInterval(transcriptPoll);
    transcriptPoll = null;
  }
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

  setVoiceStatus('Connecting to NammaResolve...');

  try {
    console.log('[1] Requesting Agora session...');

    const response = await fetch('/api/voice/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({language: selectedVoiceLanguage})
    });

    const data = await response.json();

    console.log('[2] Backend response:', {
      status: response.status,
      app_id: data.app_id,
      channel: data.channel,
      uid: data.uid,
      agent_session_id: data.agent_session_id
    });

    if (!response.ok) {
      throw new Error(data.detail || 'Session creation failed');
    }

    if (!window.AgoraRTC) {
      throw new Error('AgoraRTC SDK did not load. Refresh the page and check your network or content blocker.');
    }

    console.log('[3] Creating Agora RTC client...');

    rtcClient = AgoraRTC.createClient({
      mode: 'rtc',
      codec: 'vp8'
    });

    rtcClient.on('user-published', async (user, mediaType) => {
      console.log('[4] Remote user published:', user.uid, mediaType);

      await rtcClient.subscribe(user, mediaType);

      if (mediaType === 'audio') {
        user.audioTrack.play();
        console.log('[5] Remote audio playing');
      }
    });

    rtcClient.on('user-left', (user) => {
      console.log('[6] Remote user left:', user.uid);
    });

    rtcClient.on('connection-state-change', (cur, prev, reason) => {
      console.log('[RTC connection]', prev, '->', cur, reason);
    });

    console.log('[7] Joining Agora channel...');

    await rtcClient.join(
      data.app_id,
      data.channel,
      data.token,
      data.uid
    );

    console.log('[8] Agora channel joined');

    console.log('[9] Requesting microphone...');

    localAudioTrack =
      await AgoraRTC.createMicrophoneAudioTrack();

    console.log('[10] Microphone acquired');

    await rtcClient.publish([localAudioTrack]);

    console.log('[11] Microphone published successfully');

    activeAgentSessionId = data.agent_session_id;

    await appendTranscript('system', `Conversation started in ${selectedVoiceLanguage === 'kn-IN' ? 'Kannada' : 'English'}.`);
    await refreshTranscript();
    transcriptPoll = setInterval(refreshTranscript, 1500);

    $('#voiceButton').classList.add('active');
    button.textContent = 'End conversation';

    setVoiceStatus('Connected. NammaResolve is speaking through Murf—tell us what happened.');

  } catch (error) {
    console.error('[NAMMARESOLVE VOICE ERROR]', error);

    if (localAudioTrack) {
      localAudioTrack.stop();
      localAudioTrack.close();
      localAudioTrack = null;
    }

    if (rtcClient) {
      try {
        await rtcClient.leave();
      } catch (cleanupError) {
        console.error('RTC cleanup error:', cleanupError);
      }
      rtcClient = null;
    }

    setVoiceStatus(error.message || 'Voice connection failed.');
    button.textContent = 'Try again ↗';

  } finally {
    button.disabled = false;
  }
}


document.querySelectorAll('.language-option').forEach((option) => {
  option.addEventListener('click', () => {
    if (rtcClient) return;
    selectedVoiceLanguage = option.dataset.language;
    document.querySelectorAll('.language-option').forEach((item) => {
      const active = item === option;
      item.classList.toggle('active', active);
      item.setAttribute('aria-checked', String(active));
    });
    setVoiceStatus(selectedVoiceLanguage === 'kn-IN'
      ? 'Kannada selected. Start conversation and speak in Kannada.'
      : 'English selected. Start conversation and speak in English.');
  });
});

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
loadPocs();
document.querySelectorAll('.issue-chip').forEach((chip) => chip.addEventListener('click', () => {
  $('#category').value = chip.dataset.category;
  document.querySelectorAll('.issue-chip').forEach((item) => item.classList.remove('selected'));
  chip.classList.add('selected');
  $('#report').scrollIntoView({ behavior: 'smooth', block: 'center' });
}));

loadReports();
