import SwiftUI

struct QuoteHeaderView: View {
    let quote: QuoteModel

    private var changeColor: Color {
        quote.changePct > 0 ? .red : quote.changePct < 0 ? .green : .primary
    }

    var body: some View {
        VStack(spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(quote.name).font(.headline)
                Text(quote.ticker).font(.subheadline).foregroundColor(.secondary)
                Spacer()
                Text(String(format: "%.2f", quote.close))
                    .font(.title2.bold())
                    .foregroundColor(changeColor)
            }
            HStack {
                Text(String(format: "%+.2f（%.2f%%）", quote.change, quote.changePct))
                    .font(.subheadline).foregroundColor(changeColor)
                Spacer()
                Text("量 \(quote.volume / 1000) 張")
                    .font(.caption).foregroundColor(.secondary)
            }
            HStack(spacing: 16) {
                ohlcItem("開", quote.open)
                ohlcItem("高", quote.high)
                ohlcItem("低", quote.low)
                Spacer()
            }
            .font(.caption)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color.secondary.opacity(0.1))
    }

    private func ohlcItem(_ label: String, _ value: Double) -> some View {
        HStack(spacing: 2) {
            Text(label).foregroundColor(.secondary)
            Text(String(format: "%.2f", value))
        }
    }
}
