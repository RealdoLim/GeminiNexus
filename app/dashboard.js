async function fetchBootstrap() {
  const res = await fetch("/api/bootstrap");
  return res.json();
}

function renderGuardrailStatus(result) {
  const status = document.getElementById("guardrailStatus");
  const categories = document.getElementById("guardrailCategories");

  if (!status || !categories) return;

  if (!result) {
    status.textContent = "Mission validation not checked yet.";
    status.className = "guardrail-status";
    categories.innerHTML = "";
    return;
  }

  status.textContent = result.safe_message;
  status.className = result.allowed
    ? "guardrail-status ok"
    : "guardrail-status blocked";

  if (result.categories && result.categories.length > 0) {
    categories.innerHTML = result.categories
      .map(category => `<span class="guardrail-badge">${category}</span>`)
      .join("");
  } else {
    categories.innerHTML = `<span class="guardrail-badge ok">validation_passed</span>`;
  }
}

async function postAction(url) {
  const res = await fetch(url, { method: "POST" });
  return res.json();
}
function renderSummary(summary) {
  const container = document.getElementById("summaryCards");
  const cards = [
    ["Mission ID", summary.mission_id],
    ["Coordinator", summary.coordinator_name],
    ["Location", `${summary.city}, ${summary.country}`],
    ["Minutes to Maghrib", summary.minutes_to_maghrib],
    ["Safe Packages", summary.total_packages_safe],
    ["Blocked Packages", summary.blocked_packages],
    ["Distribution Points", summary.total_distribution_points],
    ["Volunteers", `${summary.available_volunteers}/${summary.total_volunteers}`],
    ["Households", summary.total_households],
    ["Assigned Packages", summary.assigned_packages],
    ["Assignments", summary.assignment_count],
    ["Incidents", summary.incident_count]
  ];

  container.innerHTML = cards.map(([label, value]) => `
    <div class="card">
      <div class="card-label">${label}</div>
      <div class="card-value">${value}</div>
    </div>
  `).join("");
}

function renderTable(containerId, rows, columns) {
  const container = document.getElementById(containerId);

  if (!rows || rows.length === 0) {
    container.innerHTML = `<p class="empty-state">No data yet.</p>`;
    return;
  }

  const header = columns.map(col => `<th>${col.label}</th>`).join("");
  const body = rows.map(row => `
    <tr>
      ${columns.map(col => `<td>${row[col.key] ?? "-"}</td>`).join("")}
    </tr>
  `).join("");

  container.innerHTML = `
    <table>
      <thead><tr>${header}</tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function renderLogs(logs) {
  const container = document.getElementById("logStream");
  container.innerHTML = logs.map(log => `
    <div class="log-line">
      <span class="log-time">${log.timestamp}</span>
      <span class="log-agent">${log.agent}</span>
      <span class="log-message">${log.message}</span>
    </div>
  `).join("");
}

function renderNotifications(notifications) {
  const container = document.getElementById("notificationsPanel");

  if (!notifications || notifications.length === 0) {
    container.innerHTML = `<p class="empty-state">No notifications yet.</p>`;
    return;
  }

  container.innerHTML = notifications.map(notification => `
    <div class="feed-item">
      <div class="feed-title">${notification.target_type}:${notification.target_id}</div>
      <div class="feed-text">${notification.message}</div>
    </div>
  `).join("");
}

function renderIncidents(incidents) {
  const container = document.getElementById("incidentsPanel");

  if (!incidents || incidents.length === 0) {
    container.innerHTML = `<p class="empty-state">No incidents yet.</p>`;
    return;
  }

  container.innerHTML = incidents.map(incident => `
    <div class="feed-item">
      <div class="feed-title">${incident.type}</div>
      <div class="feed-text">
        ${(incident.volunteer_name ?? incident.point_name ?? "-")} —
        status: ${incident.status ?? "-"}
      </div>
    </div>
  `).join("");
}

async function refreshDashboard() {
  const data = await fetchBootstrap();

    renderSummary(data.summary);
    renderGuardrailStatus(data.guardrail);

  renderTable("pointsTable", data.distribution_points, [
    { key: "name", label: "Name" },
    { key: "address", label: "Address" },
    { key: "capacity", label: "Capacity" },
    { key: "assigned_packages", label: "Assigned Packages" },
    { key: "status", label: "Status" }
  ]);

  renderTable("volunteersTable", data.volunteers, [
    { key: "name", label: "Volunteer" },
    { key: "location", label: "Location" },
    { key: "vehicle_capacity", label: "Vehicle Capacity" },
    { key: "assigned_point_id", label: "Assigned Point" },
    { key: "status", label: "Status" }
  ]);

  renderTable("routesTable", data.route_plans, [
    { key: "point_name", label: "Point" },
    { key: "households", label: "Households" },
    { key: "allocated_packages", label: "Allocated Packages" },
    { key: "status", label: "Status" }
  ]);

    const assignmentRows = (data.volunteer_assignments || []).map(row => ({
    ...row,
    distance_km: row.distance_meters != null ? (row.distance_meters / 1000).toFixed(1) : "-",
    travel_min: row.duration_seconds != null ? Math.round(row.duration_seconds / 60) : "-"
  }));

  renderTable("assignmentsTable", assignmentRows, [
    { key: "volunteer_name", label: "Volunteer" },
    { key: "point_name", label: "Point" },
    { key: "packages_assigned", label: "Packages" },
    { key: "trips_required", label: "Trips" },
    { key: "travel_min", label: "ETA (min)" },
    { key: "distance_km", label: "Distance (km)" },
    { key: "status", label: "Status" }
  ]);

  renderTable("recipientsTable", data.recipient_clusters, [
    { key: "area_name", label: "Area" },
    { key: "point_id", label: "Point" },
    { key: "households", label: "Households" },
    { key: "status", label: "Status" }
  ]);

  renderNotifications(data.notifications);
  renderIncidents(data.incidents);
  renderLogs(data.logs);
}

document.getElementById("launchBtn").addEventListener("click", async () => {
  const result = await postAction("/api/launch");
  if (result.guardrail) renderGuardrailStatus(result.guardrail);
  await refreshDashboard();
});

document.getElementById("cancelVolunteerBtn").addEventListener("click", async () => {
  const result = await postAction("/api/incidents/volunteer-cancel");
  if (result.guardrail) renderGuardrailStatus(result.guardrail);
  await refreshDashboard();
});

document.getElementById("maghribBtn").addEventListener("click", async () => {
  const result = await postAction("/api/incidents/maghrib-critical");
  if (result.guardrail) renderGuardrailStatus(result.guardrail);
  await refreshDashboard();
});

document.getElementById("resetBtn").addEventListener("click", async () => {
  await postAction("/api/reset");
  await refreshDashboard();
});

refreshDashboard();