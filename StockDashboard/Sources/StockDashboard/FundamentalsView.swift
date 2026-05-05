import SwiftUI

struct FundamentalsView: View {
    @EnvironmentObject var service: NetworkService

    var body: some View {
        List {
            Section("估值指標") {
                if let v = service.valuation {
                    row("本益比 P/E", value: v.pe.map { String(format: "%.2f 倍", $0) } ?? "—")
                    row("股價淨值比 P/B", value: v.pb.map { String(format: "%.2f 倍", $0) } ?? "—")
                    row("殖利率", value: v.dividendYield.map { String(format: "%.2f%%", $0) } ?? "—")
                } else if service.isLoading {
                    HStack { Spacer(); ProgressView(); Spacer() }
                } else {
                    Text("無資料（僅上市股票支援）").foregroundColor(.secondary)
                }
            }
        }
        .listStyle(.inset)
    }

    private func row(_ label: String, value: String) -> some View {
        HStack {
            Text(label).foregroundColor(.secondary)
            Spacer()
            Text(value).bold()
        }
    }
}
