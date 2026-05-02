let stream;
function startCamera() {
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(s => {
            stream = s;
            document.getElementById('videoElement').srcObject = s;
            document.getElementById('startCamera').style.display = 'none';
            document.getElementById('stopCamera').style.display = 'inline-block';
            document.getElementById('analyzeButton').style.display = 'inline-block';
        });
}
function stopCamera() {
    if (stream) stream.getTracks().forEach(t => t.stop());
    document.getElementById('startCamera').style.display = 'inline-block';
    document.getElementById('stopCamera').style.display = 'none';
    document.getElementById('analyzeButton').style.display = 'none';
}
function analyzeFrame() {
    const video = document.getElementById('videoElement');
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const frameData = canvas.toDataURL('image/jpeg');
    fetch('/analyze-interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame: frameData })
    })
    .then(r => r.json())
    .then(data => {
        $('#analysisResults').html(`
            <p>Posture: ${data.posture_score.toFixed(1)}%</p>
            <p>Eye Contact: ${data.eye_contact_score.toFixed(1)}%</p>
            <p>Body Language: ${data.body_language_score.toFixed(1)}%</p>
            <p>Feedback: ${data.feedback.join(', ')}</p>
        `);
    });
}
// Enroll button handler for dynamic courses
$(document).on('click', '.enroll-btn', function() {
    const btn = $(this);
    btn.prop('disabled', true).text('Enrolling...');
    $.ajax({
        url: '/enroll-external',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            platform: btn.data('platform'),
            source_id: btn.data('source')
        }),
        success: function(res) {
            window.location.href = res.redirect;
        },
        error: function() {
            alert('Enrollment failed');
            btn.prop('disabled', false).text('Start Course');
        }
    });
});