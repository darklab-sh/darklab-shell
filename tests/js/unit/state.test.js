import { fromScript } from './helpers/extract.js'

describe('composer state store', () => {
  function loadStateHelpers() {
    return fromScript(
      'app/static/js/state.js',
      'getComposerState',
      'setComposerState',
      'resetComposerState',
    )
  }

  it('stores composer value, selection, and active input without touching the DOM', () => {
    const { getComposerState, setComposerState } = loadStateHelpers()

    const next = setComposerState({
      value: 'ping darklab.sh',
      selectionStart: 4,
      selectionEnd: 8,
      activeInput: 'mobile',
    })

    expect(next).toEqual({
      value: 'ping darklab.sh',
      selectionStart: 4,
      selectionEnd: 8,
      activeInput: 'mobile',
    })
    expect(getComposerState()).toEqual(next)
  })

  it('resets composer state back to the defaults', () => {
    const { getComposerState, setComposerState, resetComposerState } = loadStateHelpers()

    setComposerState({
      value: 'hostname',
      selectionStart: 3,
      selectionEnd: 8,
      activeInput: 'mobile',
    })

    expect(resetComposerState()).toEqual({
      value: '',
      selectionStart: 0,
      selectionEnd: 0,
      activeInput: 'desktop',
    })
    expect(getComposerState()).toEqual({
      value: '',
      selectionStart: 0,
      selectionEnd: 0,
      activeInput: 'desktop',
    })
  })
})
