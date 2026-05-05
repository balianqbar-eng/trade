import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var service: NetworkService
    @State private var health: HealthResponse?
    @State private var isSwitching = false
    @State private var message: String?

    var body: some View {
        List {
            Section("資料來源") {
                if let h = health {
                    ForEach(h.available, id: \.self) { provider in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(providerLabel(provider)).font(.body)
                                Text(provider).font(.caption).foregroundColor(.secondary)
                            }
                            Spacer()
                            if h.provider == provider {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.blue)
                            } else {
                                Button("切換") {
                                    Task { await switchProvider(provider) }
                                }
                                .buttonStyle(.bordered)
                                .disabled(isSwitching)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                } else {
                    HStack { Spacer(); ProgressView(); Spacer() }
                }
            }

            Section("連線狀態") {
                if let h = health {
                    row("目前來源", h.providerLabel)
                    row("資料連線", h.connected ? "正常" : "離線",
                        color: h.connected ? .green : .red)
                } else {
                    Text("讀取中…").foregroundColor(.secondary)
                }
                if let msg = message {
                    Text(msg).foregroundColor(.secondary).font(.caption)
                }
            }

            Section("伺服器") {
                row("位址", "http://localhost:8000")
                Button("重新整理") { Task { await fetchHealth() } }
            }
        }
        .listStyle(.inset)
        .navigationTitle("設定")
        .task { await fetchHealth() }
    }

    private func fetchHealth() async {
        guard let url = URL(string: "http://localhost:8000/health") else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: url),
              let result = try? JSONDecoder().decode(HealthResponse.self, from: data) else { return }
        health = result
    }

    private func switchProvider(_ name: String) async {
        isSwitching = true
        message = nil
        guard let url = URL(string: "http://localhost:8000/provider/\(name)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        if let (data, _) = try? await URLSession.shared.data(for: req),
           let result = try? JSONDecoder().decode(HealthResponse.self, from: data) {
            health?.provider = result.provider
            health?.connected = result.connected
            message = "已切換至 \(providerLabel(result.provider))"
        } else {
            message = "切換失敗，請確認伺服器狀態"
        }
        isSwitching = false
    }

    private func providerLabel(_ name: String) -> String {
        switch name {
        case "xq":      return "XQ 全球贏家"
        case "shioaji": return "永豐金證券"
        default:        return name
        }
    }

    private func row(_ label: String, _ value: String, color: Color = .primary) -> some View {
        HStack {
            Text(label).foregroundColor(.secondary)
            Spacer()
            Text(value).foregroundColor(color)
        }
    }
}

struct HealthResponse: Codable {
    var provider: String
    var connected: Bool
    var available: [String]

    var providerLabel: String {
        switch provider {
        case "xq":      return "XQ 全球贏家"
        case "shioaji": return "永豐金證券"
        default:        return provider
        }
    }
}
