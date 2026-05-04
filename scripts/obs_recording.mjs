#!/usr/bin/env node

import { createHash, randomUUID } from 'node:crypto'

const DEFAULT_OBS_WS_URL = 'ws://127.0.0.1:4455'
const REQUEST_TIMEOUT_MS = 10_000

function usage() {
  console.log(`Usage: node scripts/obs_recording.mjs <command>

Commands:
  status       Print the current OBS recording status.
  assert-idle  Exit non-zero if OBS is already recording.
  start        Start OBS recording.
  stop         Stop OBS recording and print the output path when OBS returns one.

Environment:
  OBS_WS_URL       OBS WebSocket URL. Default: ${DEFAULT_OBS_WS_URL}
  OBS_WS_PASSWORD  OBS WebSocket password, if authentication is enabled.
`)
}

function sha256Base64(value) {
  return createHash('sha256').update(value).digest('base64')
}

function obsAuth(password, salt, challenge) {
  const secret = sha256Base64(`${password}${salt}`)
  return sha256Base64(`${secret}${challenge}`)
}

async function eventDataToString(data) {
  if (typeof data === 'string') return data
  if (data instanceof ArrayBuffer) return Buffer.from(data).toString('utf8')
  if (ArrayBuffer.isView(data)) {
    return Buffer.from(data.buffer, data.byteOffset, data.byteLength).toString('utf8')
  }
  if (data && typeof data.text === 'function') return data.text()
  return String(data)
}

class ObsWebSocketClient {
  constructor({ url, password }) {
    this.url = url
    this.password = password
    this.ws = null
    this.pending = new Map()
  }

  connect() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url)
      this.ws = ws
      let identified = false
      const fail = (error) => {
        if (!identified) reject(error)
      }

      ws.addEventListener('error', () => {
        fail(new Error(`Could not connect to OBS WebSocket at ${this.url}. Is OBS running with WebSocket enabled?`))
      })
      ws.addEventListener('close', () => {
        if (!identified) fail(new Error(`OBS WebSocket closed before identifying at ${this.url}.`))
      })
      ws.addEventListener('message', async (event) => {
        let message
        try {
          message = JSON.parse(await eventDataToString(event.data))
        } catch (error) {
          fail(new Error(`Could not parse OBS WebSocket message: ${error.message}`))
          return
        }

        if (message.op === 0) {
          try {
            this.identify(message.d || {})
          } catch (error) {
            fail(error)
          }
          return
        }

        if (message.op === 2) {
          identified = true
          resolve()
          return
        }

        if (message.op === 7) {
          this.handleRequestResponse(message.d || {})
        }
      })
    })
  }

  identify(hello) {
    const payload = {
      rpcVersion: Math.min(Number(hello.rpcVersion || 1), 1),
      eventSubscriptions: 0,
    }
    if (hello.authentication) {
      if (!this.password) {
        throw new Error('OBS WebSocket requires a password. Set OBS_WS_PASSWORD and try again.')
      }
      payload.authentication = obsAuth(
        this.password,
        hello.authentication.salt || '',
        hello.authentication.challenge || '',
      )
    }
    this.send(1, payload)
  }

  handleRequestResponse(data) {
    const requestId = data.requestId
    const pending = this.pending.get(requestId)
    if (!pending) return
    clearTimeout(pending.timeout)
    this.pending.delete(requestId)

    if (data.requestStatus && data.requestStatus.result) {
      pending.resolve(data.responseData || {})
      return
    }

    const comment = data.requestStatus?.comment || 'OBS request failed.'
    const code = data.requestStatus?.code ? ` (${data.requestStatus.code})` : ''
    pending.reject(new Error(`${comment}${code}`))
  }

  send(op, data) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('OBS WebSocket is not open.')
    }
    this.ws.send(JSON.stringify({ op, d: data }))
  }

  request(requestType, requestData = {}) {
    const requestId = randomUUID()
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(requestId)
        reject(new Error(`Timed out waiting for OBS response to ${requestType}.`))
      }, REQUEST_TIMEOUT_MS)
      this.pending.set(requestId, { resolve, reject, timeout })
      this.send(6, { requestType, requestId, requestData })
    })
  }

  close() {
    if (this.ws) this.ws.close()
  }
}

async function withObs(callback) {
  const client = new ObsWebSocketClient({
    url: process.env.OBS_WS_URL || DEFAULT_OBS_WS_URL,
    password: process.env.OBS_WS_PASSWORD || '',
  })
  await client.connect()
  try {
    return await callback(client)
  } finally {
    client.close()
  }
}

function printStatus(status) {
  const active = status.outputActive ? 'yes' : 'no'
  const paused = status.outputPaused ? 'yes' : 'no'
  const path = status.outputPath ? `\nOutput path: ${status.outputPath}` : ''
  console.log(`OBS recording active: ${active}
OBS recording paused: ${paused}${path}`)
}

async function main() {
  const command = process.argv[2]
  if (!command || command === '--help' || command === '-h') {
    usage()
    return
  }

  await withObs(async (client) => {
    if (command === 'status') {
      printStatus(await client.request('GetRecordStatus'))
      return
    }

    if (command === 'assert-idle') {
      const status = await client.request('GetRecordStatus')
      if (status.outputActive) {
        throw new Error('OBS is already recording. Stop the current recording before running the demo wrapper.')
      }
      console.log('OBS recording is idle.')
      return
    }

    if (command === 'start') {
      const status = await client.request('GetRecordStatus')
      if (status.outputActive) {
        throw new Error('OBS is already recording. Stop the current recording before starting a demo recording.')
      }
      await client.request('StartRecord')
      console.log('OBS recording started.')
      return
    }

    if (command === 'stop') {
      const status = await client.request('GetRecordStatus')
      if (!status.outputActive) {
        console.log('OBS was not recording.')
        return
      }
      const response = await client.request('StopRecord')
      const outputPath = response.outputPath || response.output_path || ''
      console.log(outputPath ? `OBS recording stopped: ${outputPath}` : 'OBS recording stopped.')
      return
    }

    throw new Error(`Unknown command: ${command}`)
  })
}

main().catch((error) => {
  console.error(`[obs] ${error.message}`)
  process.exit(1)
})
