import { makeTestIp } from './helpers.js'

export const CMD = 'curl http://localhost:5001/health'
export const TEST_IP = makeTestIp(68)

export async function setupWelcomePage(page) {
  await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
  await page.route('**/welcome', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          cmd: 'echo ready',
          group: 'basics',
          featured: true,
          out: 'welcome should disappear if the user starts typing',
        },
        {
          cmd: 'dig darklab.sh A',
          out: 'second sample should appear instantly when welcome settles',
        },
      ]),
    })
  })
  await page.route('**/welcome/ascii', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/plain',
      body: [
        '           /$$                 /$$ /$$           /$$                     /$$       /$$           /$$                    /$$      ',
        '          | $$                | $$| $$          | $$                    | $$      | $$          | $$                   | $$      ',
      ].join('\n'),
    })
  })
  await page.route('**/welcome/ascii-mobile', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/plain',
      body: [
        '.----[ darklab_shell :: mobile console ]----.',
        '|                                              |',
        '|   __  __   ___   ___   ___   ___   ___       |',
        '|  |  \\/  | / _ \\ / _ \\ / _ \\ / _ \\ / _ \\      |',
        '|  | |\\/| || (_) | (_) | (_) | (_) | (_) |     |',
        '|  |_|  |_| \\___/ \\___/ \\___/ \\___/ \\___/      |',
        '|                                              |',
        "'----[ status: ready ]----[ prompt: anon@darklab:~$ ]----'",
      ].join('\n'),
    })
  })
  await page.route('**/welcome/hints', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: ['Use the history panel to reopen saved runs.'],
      }),
    })
  })
  await page.route('**/welcome/hints-mobile', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: ['Tap the prompt to open the mobile keyboard quickly.'],
      }),
    })
  })
  await page.route('**/run', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'data: {"type":"started","run_id":"welcome-test-run"}\n\n',
        'data: {"type":"output","text":"status\\n"}\n\n',
        'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
      ].join(''),
    })
  })
  await page.goto('/')
  await page.locator('#cmd').waitFor()
}
