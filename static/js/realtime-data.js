class RealTimeDataManager {
    loadMarketTrends(field) {
        fetch(`/api/market-trends?field=${field}`)
            .then(r => r.json())
            .then(data => {
                let html = '<div class="list-group">';
                if (data.trending_skills.length) {
                    data.trending_skills.slice(0,8).forEach(skill => {
                        html += `<div class="list-group-item d-flex justify-content-between">
                            <span>${skill.skill}</span>
                            <span class="badge bg-primary">${skill.count} jobs</span>
                        </div>`;
                    });
                } else {
                    html += '<div class="list-group-item">No data available</div>';
                }
                html += '</div>';
                $('#trending-tech').html(html);
            });
    }
    loadLiveCertifications(field, level) {
        fetch(`/api/live-certifications?field=${field}&level=${level}`)
            .then(r => r.json())
            .then(certs => {
                let html = '<div class="row">';
                certs.forEach(c => {
                    html += `<div class="col-md-6 mb-2">
                        <div class="card p-2">
                            <h6>${c.name}</h6>
                            <span class="badge bg-secondary">${c.platform}</span>
                            <button class="btn btn-sm btn-primary mt-2 enroll-btn"
                                data-platform="${c.enrollment.platform}"
                                data-source="${c.enrollment.source_id}">Start Course</button>
                        </div>
                    </div>`;
                });
                html += '</div>';
                $('#live-certifications').html(html);
            });
    }
    loadResumeTemplates(field) {
        fetch(`/api/resume-templates?field=${field}`)
            .then(r => r.json())
            .then(templates => {
                let html = '<ul class="list-group">';
                templates.forEach(t => {
                    html += `<li class="list-group-item">
                        <a href="${t.url}" target="_blank">${t.name}</a>
                        <span class="float-end">⭐ ${t.stars}</span>
                    </li>`;
                });
                html += '</ul>';
                $('#resume-templates').html(html);
            });
    }
    loadJobListings(field) {
        fetch(`/api/job-listings?field=${field}`)
            .then(r => r.json())
            .then(jobs => {
                let html = '';
                jobs.forEach(job => {
                    html += `<div class="list-group-item">
                        <strong>${job.title}</strong> at ${job.company}
                        <br><small>${job.location}</small>
                        <span class="float-end text-success">${job.salary || ''}</span>
                    </div>`;
                });
                $('#live-jobs').html(html);
            });
    }
}