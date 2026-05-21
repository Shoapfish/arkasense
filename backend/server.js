const express    = require('express')
const http       = require('http')
const { Server } = require('socket.io')
const cors       = require('cors')
const crypto     = require('crypto') // Built-in node module for safe token generation

const app    = express()
const server = http.createServer(app)
const io     = new Server(server, {
  cors: { origin: "*" }
})

app.use(cors())
app.use(express.json())

// ─────────────────────────────────────────
// Admin Configuration & Auth State
// ─────────────────────────────────────────
// Fallback password is 'admin123' if ADMIN_PASSWORD isn't set in your Render environment variables
const ADMIN_USERNAME = process.env.ADMIN_USER || 'admin'
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123' 

// In-memory store for active session tokens
const activeTokens = new Set()

// Middleware to protect admin routes
function requireAdmin(req, res, next) {
  const token = req.headers['x-admin-token']
  if (!token || !activeTokens.has(token)) {
    return res.status(401).json({ ok: false, error: 'Unauthorized administrative access' })
  }
  next()
}

// ─────────────────────────────────────────
// In-memory state
// ─────────────────────────────────────────
let currentSlots = {
  S1: "free", S2: "free", S3: "free",
  S4: "free", S5: "free", S6: "free"
}

// reservations[slotName] = { name, plate, phone, reservedAt, expiresAt, code }
let reservations = {}

let eventLog = []
let reservationLog = []

// ─────────────────────────────────────────
// Helper: generate simple 6-char code
// ─────────────────────────────────────────
function generateCode() {
  return Math.random().toString(36).substring(2, 8).toUpperCase()
}

// ─────────────────────────────────────────
// Helper: broadcast full state to all clients
// ─────────────────────────────────────────
function broadcastState(changes = []) {
  const available = Object.entries(currentSlots)
    .filter(([slot, s]) => s === "free" && !reservations[slot]).length

  io.emit('slot-update', {
    slots: currentSlots,
    reservations,
    available,
    total: Object.keys(currentSlots).length,
    changes,
    log: eventLog.slice(0, 20),
    reservationLog: reservationLog.slice(0, 20)
  })
}

// ─────────────────────────────────────────
// Auto-expire reservations every 30s
// ─────────────────────────────────────────
setInterval(() => {
  const now = Date.now()
  let changed = false
  for (const [slot, res] of Object.entries(reservations)) {
    if (res.expiresAt < now) {
      reservationLog.unshift({
        slot,
        name: res.name,
        action: 'expired',
        timestamp: new Date().toLocaleString('en-PH')
      })
      delete reservations[slot]
      changed = true
      console.log(`Reservation for ${slot} expired.`)
    }
  }
  if (changed) broadcastState()
}, 30000)

// ─────────────────────────────────────────
// Admin Authentication Endpoints
// ─────────────────────────────────────────

// POST /admin/login
app.post('/admin/login', (req, res) => {
  const { username, password } = req.body

  if (username === ADMIN_USERNAME && password === ADMIN_PASSWORD) {
    // Generate a secure, unique dynamic token for this session
    const token = crypto.randomBytes(24).toString('hex')
    activeTokens.add(token)
    return res.json({ ok: true, token })
  }

  res.status(401).json({ ok: false, error: 'Invalid username or password' })
})

// GET /admin/verify
app.get('/admin/verify', (req, res) => {
  const token = req.headers['x-admin-token']
  if (token && activeTokens.has(token)) {
    return res.json({ ok: true })
  }
  res.json({ ok: false })
})

// POST /admin/logout
app.post('/admin/logout', (req, res) => {
  const token = req.headers['x-admin-token']
  if (token) {
    activeTokens.delete(token)
  }
  res.json({ ok: true })
})

// ─────────────────────────────────────────
// Admin Actions Endpoints
// ─────────────────────────────────────────

// POST /admin/reservation/accept
app.post('/admin/reservation/accept', requireAdmin, (req, res) => {
  const { slot } = req.body
  if (!reservations[slot]) {
    return res.status(404).json({ ok: false, error: 'No reservation active for this slot' })
  }
  
  // Note: Your frontend keeps tracking confirmation status through acceptedSlots local state
  console.log(`Admin approved reservation on Slot ${slot}`)
  res.json({ ok: true })
})

// POST /admin/reservation/reject
app.post('/admin/reservation/reject', requireAdmin, (req, res) => {
  const { slot } = req.body
  if (!reservations[slot]) {
    return res.status(404).json({ ok: false, error: 'No reservation found' })
  }

  const name = reservations[slot].name
  reservationLog.unshift({
    slot,
    name,
    action: 'cancelled', // Triggers the custom 'resout' red border accent in UI logs
    timestamp: new Date().toLocaleString('en-PH')
  })

  delete reservations[slot]
  broadcastState()
  res.json({ ok: true })
})

// POST /admin/reservation/cancel (Handles dashboard layout Force-Cancel button)
app.post('/admin/reservation/cancel', requireAdmin, (req, res) => {
  const { slot } = req.body
  if (!reservations[slot]) {
    return res.status(404).json({ ok: false, error: 'No reservation to cancel' })
  }

  const name = reservations[slot].name
  reservationLog.unshift({
    slot, 
    name, 
    action: 'admin-cancelled',
    timestamp: new Date().toLocaleString('en-PH')
  })

  delete reservations[slot]
  broadcastState()
  res.json({ ok: true })
})

// ─────────────────────────────────────────
// POST /update-slots  (from Python vision)
// ─────────────────────────────────────────
app.post('/update-slots', (req, res) => {
  const { slots, timestamp } = req.body

  const changes = []
  for (const [slot, status] of Object.entries(slots)) {
    if (currentSlots[slot] !== status) {
      changes.push({ slot, status, timestamp })
      eventLog.unshift({ slot, status, timestamp })

      // If slot just became occupied and was reserved → clear reservation
      if (status === 'occupied' && reservations[slot]) {
        reservationLog.unshift({
          slot,
          name: reservations[slot].name,
          action: 'fulfilled',
          timestamp
        })
        delete reservations[slot]
      }
    }
  }

  currentSlots = { ...slots }
  broadcastState(changes)
  const available = Object.entries(currentSlots)
    .filter(([slot, s]) => s === "free" && !reservations[slot]).length
  res.json({ ok: true, available })
})

// ─────────────────────────────────────────
// GET /status  (initial load for dashboards)
// ─────────────────────────────────────────
app.get('/status', (req, res) => {
  const available = Object.entries(currentSlots)
    .filter(([slot, s]) => s === "free" && !reservations[slot]).length
  res.json({
    slots: currentSlots,
    reservations,
    available,
    total: Object.keys(currentSlots).length,
    log: eventLog,
    reservationLog
  })
})

// ─────────────────────────────────────────
// POST /reserve  (user reserves a slot)
// ─────────────────────────────────────────
app.post('/reserve', (req, res) => {
  const { slot, name, plate, phone, duration = 30 } = req.body

  if (!slot || !name || !plate) {
    return res.status(400).json({ ok: false, error: 'slot, name, and plate are required' })
  }

  if (!currentSlots[slot]) {
    return res.status(400).json({ ok: false, error: 'Invalid slot' })
  }

  if (currentSlots[slot] === 'occupied') {
    return res.status(409).json({ ok: false, error: 'Slot is currently occupied' })
  }

  if (reservations[slot]) {
    return res.status(409).json({ ok: false, error: 'Slot is already reserved' })
  }

  const code = generateCode()
  const now = Date.now()
  const durationMs = Math.min(Math.max(duration, 5), 600) * 60 * 1000 // 5 min–10 hr clamp

  reservations[slot] = {
    name,
    plate: plate.toUpperCase(),
    phone: phone || '',
    reservedAt: new Date(now).toLocaleString('en-PH'),
    expiresAt: now + durationMs,
    expiresAtDisplay: new Date(now + durationMs).toISOString(),
    code,
    duration: Math.min(Math.max(duration, 5), 600)
  }

  reservationLog.unshift({
    slot,
    name,
    plate: plate.toUpperCase(),
    action: 'reserved',
    timestamp: new Date().toLocaleString('en-PH')
  })

  console.log(`Reservation: ${slot} → ${name} (${plate}) for ${duration}min [${code}]`)
  broadcastState()

  res.json({ ok: true, code, slot, expiresAt: new Date(now + durationMs).toISOString() })
})

// ─────────────────────────────────────────
// DELETE /reserve/:slot  (user cancel via code)
// ─────────────────────────────────────────
app.delete('/reserve/:slot', (req, res) => {
  const { slot } = req.params
  const { code } = req.body

  if (!reservations[slot]) {
    return res.status(404).json({ ok: false, error: 'No reservation found for this slot' })
  }

  if (reservations[slot].code !== code) {
    return res.status(403).json({ ok: false, error: 'Invalid cancellation code' })
  }

  const name = reservations[slot].name
  reservationLog.unshift({
    slot,
    name,
    action: 'cancelled',
    timestamp: new Date().toLocaleString('en-PH')
  })

  delete reservations[slot]
  broadcastState()

  res.json({ ok: true, message: 'Reservation cancelled' })
})

// ─────────────────────────────────────────
// Legacy Admin Endpoint Compatibility
// ─────────────────────────────────────────
app.delete('/admin/reserve/:slot', requireAdmin, (req, res) => {
  const { slot } = req.params
  if (!reservations[slot]) {
    return res.status(404).json({ ok: false, error: 'No reservation' })
  }
  const name = reservations[slot].name
  reservationLog.unshift({
    slot, name, action: 'admin-cancelled',
    timestamp: new Date().toLocaleString('en-PH')
  })
  delete reservations[slot]
  broadcastState()
  res.json({ ok: true })
})

// ─────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────
io.on('connection', (socket) => {
  console.log('Client connected:', socket.id)
  const available = Object.entries(currentSlots)
    .filter(([slot, s]) => s === "free" && !reservations[slot]).length
  socket.emit('slot-update', {
    slots: currentSlots,
    reservations,
    available,
    total: Object.keys(currentSlots).length,
    changes: [],
    log: eventLog,
    reservationLog
  })
  socket.on('disconnect', () => console.log('Client disconnected:', socket.id))
})

// ─────────────────────────────────────────
// Start
// ─────────────────────────────────────────
server.listen(3000, () => {
  console.log('ParkaSense backend running on http://localhost:3000')
})