import SwiftUI
import WidgetKit

struct HarnessTaskEntry: TimelineEntry {
    let date: Date
    let pendingCount: Int
}

struct HarnessTaskProvider: TimelineProvider {
    func placeholder(in context: Context) -> HarnessTaskEntry {
        HarnessTaskEntry(date: Date(), pendingCount: 3)
    }

    func getSnapshot(in context: Context, completion: @escaping (HarnessTaskEntry) -> Void) {
        completion(HarnessTaskEntry(date: Date(), pendingCount: 3))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<HarnessTaskEntry>) -> Void) {
        let entry = HarnessTaskEntry(date: Date(), pendingCount: UserDefaults(suiteName: "group.com.harness.mobile")?.integer(forKey: "pendingTaskCount") ?? 0)
        completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(900))))
    }
}

struct HarnessTaskWidgetView: View {
    var entry: HarnessTaskEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Harness")
                .font(.headline)
            Text("\(entry.pendingCount) 个任务待处理")
                .font(.title3)
                .bold()
            Text("点按打开任务列表")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .containerBackground(.fill.tertiary, for: .widget)
        .widgetURL(URL(string: "agentharness://tasks"))
    }
}

@main
struct HarnessTaskWidget: Widget {
    let kind = "HarnessTaskWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: HarnessTaskProvider()) { entry in
            HarnessTaskWidgetView(entry: entry)
        }
        .configurationDisplayName("Harness 任务")
        .description("查看待同步和待处理的 Harness 任务。")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
