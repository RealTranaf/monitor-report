const express = require('express');
const bodyParser = require('body-parser');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const app = express();
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json({ limit: '10mb' }));

const dbPath = path.join('/data', 'alerts.db');
const db = new sqlite3.Database(dbPath);

db.run(`
  CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    device TEXT,
    device_id TEXT,
    sensor TEXT,
    sensor_id TEXT,
    status TEXT,
    severity TEXT,
    message TEXT,
    last_value TEXT,
    priority TEXT,
    group_name TEXT,
    probe TEXT,
    down_time TEXT,
    device_url TEXT,
    sensor_url TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw TEXT
  )
`);

app.get('/health', (req, res) => res.json({status: 'ok'}));

// PRTG webhook endpoint
app.post('/webhook/prtg', (req, res) => {
  const data = req.body;
  
  // Parse fields from your exact payload
  const device = data.device || 'Unknown';
  const status = data.status || 'Unknown';
  
  // Safely decode message (handle malformed URIs)
  let message = data.message || '';
  try {
    message = decodeURIComponent(message);
  } catch (e) {
    // If decoding fails, use original
    console.log('Warning: Could not decode message, using as-is');
  }
  
  // Determine severity
  let severity = 'info';
  const statusLower = status.toLowerCase();
  if (statusLower.includes('down')) severity = 'critical';
  else if (statusLower.includes('warning')) severity = 'warning';
  else if (statusLower.includes('error')) severity = 'error';
  else if (statusLower.includes('threshold')) severity = 'warning';
  else if (statusLower.includes('breached')) severity = 'warning';
  
  // PRTG payload uses 'sensor' not 'name'
  const sensorName = data.sensor || data.name || 'Unknown';
  const sensorId = data.sensorid || null;
  const lastValue = data.lastvalue && data.lastvalue !== '' ? data.lastvalue : null;
  const downTime = data.down && data.down !== '' ? data.down : null;
  
  console.log(`[${severity.toUpperCase()}] ${device} - ${sensorName}: ${message}`);
  
  db.run(
    `INSERT INTO alerts (
      source, device, device_id, sensor, sensor_id, status, severity, 
      message, last_value, priority, group_name, probe, down_time,
      device_url, sensor_url, timestamp, raw
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      'prtg',
      device,
      data.deviceid || null,
      sensorName,
      sensorId,
      status,
      severity,
      message,
      lastValue,
      data.priority || null,
      data.group || null,
      data.probe || null,
      downTime,
      data.linkdevice || null,
      data.linksensor || null,
      data.datetime || new Date().toISOString(),
      JSON.stringify(data)
    ],
    (err) => {
      if (err) {
        console.error('DB Error:', err);
        res.status(500).json({error: err.message});
      } else {
        res.json({success: true});
      }
    }
  );
});

// Prometheus Alertmanager webhook endpoint
app.post('/webhook/prometheus', (req, res) => {
  const data = req.body;
  
  // Alertmanager sends an array of alerts
  const alerts = data.alerts || [];
  
  console.log(`[PROMETHEUS] Received ${alerts.length} alert(s)`);
  
  alerts.forEach(alert => {
    const labels = alert.labels || {};
    const annotations = alert.annotations || {};
    
    const alertName = labels.alertname || 'Unknown';
    const instance = labels.instance || 'localhost';
    const severity = labels.severity || 'warning';
    const status = alert.status || 'firing';
    const summary = annotations.summary || annotations.message || `${alertName} on ${instance}`;
    const description = annotations.description || '';
    const startsAt = alert.startsAt || new Date().toISOString();
    const endsAt = alert.endsAt;
    
    // Build full message
    const message = description ? `${summary} - ${description}` : summary;
    
    // Map prometheus severity to our format
    const severityMapped = severity === 'critical' ? 'critical' : 
                          severity === 'warning' ? 'warning' : 'info';
    
    // Status mapping
    const statusMapped = status === 'firing' ? 'firing' : 'resolved';
    
    console.log(`[${severityMapped.toUpperCase()}] ${instance} - ${alertName}: ${message}`);
    
    db.run(
      `INSERT INTO alerts (
        source, device, device_id, sensor, sensor_id, status, severity, 
        message, last_value, priority, group_name, probe, down_time,
        device_url, sensor_url, timestamp, raw
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        'prometheus',
        instance,
        null,  // device_id
        alertName,
        labels.job || null,  // sensor_id -> job
        statusMapped,
        severityMapped,
        message,
        labels.value || null,  // last_value
        severity,  // priority (raw severity)
        null,  // group_name
        null,  // probe
        null,  // down_time
        null,  // device_url
        null,  // sensor_url
        status === 'resolved' ? (endsAt || startsAt) : startsAt,
        JSON.stringify(alert)
      ],
      (err) => {
        if (err) {
          console.error('DB Error:', err);
        }
      }
    );
  });
  
  res.json({success: true, received: alerts.length});
});

app.get('/alerts', (req, res) => {
  db.all(
    `SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 20`, 
    [], 
    (err, rows) => {
      if (err) res.status(500).json({error: err.message});
      else res.json(rows);
    }
  );
});

app.get('/alerts/severity/:level', (req, res) => {
  const level = req.params.level;
  db.all(
    `SELECT * FROM alerts WHERE severity = ? ORDER BY timestamp DESC LIMIT 20`,
    [level],
    (err, rows) => {
      if (err) res.status(500).json({error: err.message});
      else res.json(rows);
    }
  );
});

const PORT = process.env.PORT || 3456;
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Alert receiver running on port ${PORT}`);
});