import { Component } from 'react'

/**
 * Render guard for the map pane. Without a boundary anywhere in the tree,
 * one throwing effect unmounts the entire app (blank page); with this, a
 * crash degrades to an error card and the rest of the UI keeps working.
 */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Render crash inside ErrorBoundary:', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
        >
          <p className="text-sm font-semibold text-slate-200">The map failed to render.</p>
          <p className="max-w-sm text-xs leading-relaxed text-slate-400">
            {String(this.state.error?.message ?? this.state.error)}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
