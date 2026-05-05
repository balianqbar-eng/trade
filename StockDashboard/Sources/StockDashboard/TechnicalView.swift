import SwiftUI

struct TechnicalView: View {
    @EnvironmentObject var service: NetworkService

    var body: some View {
        List {
            if let t = service.technical {
                Section("均線") {
                    maRow("MA 5", value: t.ma5, last: t.last)
                    maRow("MA 20", value: t.ma20, last: t.last)
                    maRow("MA 60", value: t.ma60, last: t.last)
                }
                Section("RSI（14）") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("RSI").foregroundColor(.secondary)
                            Spacer()
                            Text(String(format: "%.1f", t.rsi))
                                .foregroundColor(rsiColor(t.rsi))
                                .bold()
                            Text(rsiLabel(t.rsi))
                                .font(.caption)
                                .foregroundColor(rsiColor(t.rsi))
                        }
                        ProgressView(value: t.rsi / 100)
                            .tint(rsiColor(t.rsi))
                        HStack {
                            Text("超賣 30").font(.caption2).foregroundColor(.secondary)
                            Spacer()
                            Text("超買 70").font(.caption2).foregroundColor(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }
                Section("MACD（12, 26, 9）") {
                    valueRow("MACD", String(format: "%.4f", t.macd))
                    valueRow("Signal", String(format: "%.4f", t.signal))
                    valueRow("Histogram", String(format: "%.4f", t.histogram),
                             color: t.histogram > 0 ? .red : .green)
                }
            } else if service.isLoading {
                HStack { Spacer(); ProgressView(); Spacer() }
            } else {
                Text("無技術指標資料").foregroundColor(.secondary)
            }
        }
        .listStyle(.inset)
    }

    private func maRow(_ label: String, value: Double, last: Double) -> some View {
        HStack {
            Text(label).foregroundColor(.secondary)
            Spacer()
            Text(String(format: "%.2f", value))
            Image(systemName: last >= value ? "arrow.up" : "arrow.down")
                .font(.caption)
                .foregroundColor(last >= value ? .red : .green)
        }
    }

    private func valueRow(_ label: String, _ value: String, color: Color = .primary) -> some View {
        HStack {
            Text(label).foregroundColor(.secondary)
            Spacer()
            Text(value).foregroundColor(color).bold()
        }
    }

    private func rsiColor(_ rsi: Double) -> Color {
        if rsi >= 70 { return .red }
        if rsi <= 30 { return .green }
        return .blue
    }

    private func rsiLabel(_ rsi: Double) -> String {
        if rsi >= 70 { return "超買" }
        if rsi <= 30 { return "超賣" }
        return "正常"
    }
}
