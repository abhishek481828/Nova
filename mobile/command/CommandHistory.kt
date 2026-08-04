package com.nova.mobile.command

class CommandHistory {
    private val history = mutableListOf<CommandResult>()

    fun record(result: CommandResult) {
        history.add(result)
    }

    fun getRecentResults(limit: Int = 10): List<CommandResult> {
        return history.takeLast(limit).reversed()
    }

    fun getLastResult(): CommandResult? {
        return history.lastOrNull()
    }

    fun getTotalCount(): Int = history.size
}
