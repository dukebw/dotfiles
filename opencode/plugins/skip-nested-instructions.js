export default {
  id: "brendanduke.skip-nested-instructions",
  async setup(ctx) {
    if (process.env.OPENCODE_DISABLE_PROJECT_CONFIG !== "1") return

    // OpenCode 2.4 still attaches nested instruction files when reading project files.
    for (const kind of ["context", "compaction", "generate", "title"]) {
      await ctx.session.hook(kind, (event) => {
        event.messages = event.messages.filter(
          (message) => !Array.isArray(message.metadata?.instruction?.paths),
        )
      })
    }
  },
}
