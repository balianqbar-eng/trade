import SwiftUI

struct ChipView: View {
    @EnvironmentObject var service: NetworkService

    var body: some View {
        List {
            Section("三大法人今日買賣超（千股）") {
                if let inst = service.institutional {
                    chipRow("外資及陸資", value: inst.foreignNet)
                    chipRow("投信", value: inst.investTrustNet)
                    chipRow("自營商", value: inst.dealerNet)
                    Divider()
                    chipRow("合計", value: inst.total).fontWeight(.bold)
                } else if service.isLoading {
                    HStack { Spacer(); ProgressView(); Spacer() }
                } else {
                    Text("無資料（僅上市股票支援）").foregroundColor(.secondary)
                }
            }
        }
        .listStyle(.inset)
    }

    private func chipRow(_ label: String, value: Double) -> some View {
        HStack {
            Text(label).foregroundColor(.secondary)
            Spacer()
            Text(formatNet(value))
                .foregroundColor(value > 0 ? .red : value < 0 ? .green : .primary)
                .bold()
        }
    }

    private func formatNet(_ v: Double) -> String {
        let prefix = v > 0 ? "+" : ""
        return "\(prefix)\(Int(v).formatted())"
    }
}
