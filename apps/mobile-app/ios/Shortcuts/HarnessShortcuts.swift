import AppIntents

struct OpenHarnessTasksIntent: AppIntent {
    static var title: LocalizedStringResource = "打开 Harness 任务"
    static var description = IntentDescription("打开 Harness 移动端任务列表。")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        return .result()
    }
}

struct CreateHarnessTaskIntent: AppIntent {
    static var title: LocalizedStringResource = "新建 Harness 任务"
    static var description = IntentDescription("打开 Harness 并创建一个离线优先任务。")
    static var openAppWhenRun = true

    @Parameter(title: "标题")
    var title: String

    @Parameter(title: "目标")
    var goal: String

    func perform() async throws -> some IntentResult {
        return .result(value: "\(title): \(goal)")
    }
}

struct HarnessShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: OpenHarnessTasksIntent(),
            phrases: ["打开 \(.applicationName) 任务", "查看 \(.applicationName)"],
            shortTitle: "打开任务",
            systemImageName: "checklist"
        )
        AppShortcut(
            intent: CreateHarnessTaskIntent(),
            phrases: ["用 \(.applicationName) 新建任务"],
            shortTitle: "新建任务",
            systemImageName: "plus.circle"
        )
    }
}
