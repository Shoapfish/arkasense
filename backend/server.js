const express    = require('express')
const http       = require('http')
const { Server } = require('socket.io')
const cors       = require('cors')

const app    = express()
const server = http.createServer(app)
const io     = new Server(server, {
  cors: { origin: "*" }  // allow all origins for local dev
})

app.use(cors())
app.use(express.json())

// ─────────────────────────────────────────
// In-memory state — latest slot status
// ─────────────────────────────────────────
let currentSlots = {
  S1: "free",
  S2: "free",
  S3: "free"
}

let eventLog = []  // stores history of changes

// ─────────────────────────────────────────
// POST /update-slots
// Python vision script calls this every second
// ─────────────────────────────────────────
app.post('/update-slots', (req, res) => {
  const { slots, timestamp } = req.body

  // Detect which slots CHANGED since last update
  const changes = []
  for (const [slot, status] of Object.entries(slots)) {
    if (currentSlots[slot] !== status) {
      changes.push({ slot, status, timestamp })
      eventLog.unshift({ slot, status, timestamp }) // newest first
    }
  }

  // Update current state
  currentSlots = { ...slots }

  // Count available slots
  const available = Object.values(currentSlots)
    .filter(s => s === "free").length

  // Broadcast to ALL connected browser screens instantly
  io.emit('slot-update', {
    slots: currentSlots,
    available,
    total: 3,
    changes,
    log: eventLog.slice(0, 20) // last 20 events
  })

  res.json({ ok: true, available })
})

// ─────────────────────────────────────────
// GET /status — returns current state
// (useful for when dashboard first loads)
// ─────────────────────────────────────────
app.get('/status', (req, res) => {
  const available = Object.values(currentSlots)
    .filter(s => s === "free").length
  res.json({ slots: currentSlots, available, total: 3, log: eventLog })
})

// ─────────────────────────────────────────
// WebSocket connection event
// ─────────────────────────────────────────
io.on('connection', (socket) => {
  console.log('Screen connected:', socket.id)

  // Send current state immediately when a screen connects
  const available = Object.values(currentSlots)
    .filter(s => s === "free").length
  socket.emit('slot-update', {
    slots: currentSlots,
    available,
    total: 3,
    changes: [],
    log: eventLog
  })

  socket.on('disconnect', () => {
    console.log('Screen disconnected:', socket.id)
  })
})

// ─────────────────────────────────────────
// Start server on port 3000
// ─────────────────────────────────────────
server.listen(3000, () => {
  console.log('ParkaSense backend running on http://localhost:3000')
})