import SwiftUI

struct ContentView: View {
    @StateObject private var service = NetworkService()
    @State private var ticker = ""
    @State private var activeTicker = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                searchBar
                if service.isLoading {
                    Spacer()
                    ProgressView("載入中…")
                    Spacer()
                } else if let q = service.quote {
                    QuoteHeaderView(quote: q)
                    TabView {
                        FundamentalsView()
                            .tabItem { Label("基本面", systemImage: "chart.bar.doc.horizontal") }
                        ChipView()
                            .tabItem { Label("籌碼面", systemImage: "person.3.fill") }
                        TechnicalView()
                            .tabItem { Label("技術面", systemImage: "chart.line.uptrend.xyaxis") }
                        NewsView(ticker: activeTicker, name: q.name)
                            .tabItem { Label("消息面", systemImage: "newspaper.fill") }
                        SettingsView()
                            .tabItem { Label("設定", systemImage: "gearshape.fill") }
                    }
                } else if let err = service.error {
                    Spacer()
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)
                    Text(err).multilineTextAlignment(.center).padding().foregroundColor(.secondary)
                    Spacer()
                } else {
                    Spacer()
                    Image(systemName: "magnifyingglass.circle")
                        .font(.system(size: 60))
                        .foregroundColor(.secondary)
                    Text("輸入股票代號開始查詢").foregroundColor(.secondary).padding(.top, 8)
                    Spacer()
                }
            }
            .navigationTitle("股票儀表板")
        }
        .environmentObject(service)
        .onAppear { isFocused = true }
    }

    var searchBar: some View {
        HStack {
            TextField("股票代號（如 2330）", text: $ticker)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .focused($isFocused)
                #if os(iOS)
                .textInputAutocapitalization(.characters)
                #endif
                .onSubmit(search)
            Button("查詢", action: search)
                .buttonStyle(.borderedProminent)
        }
        .padding()
    }

    func search() {
        let t = ticker.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return }
        activeTicker = t
        Task { await service.fetchAll(ticker: t) }
    }
}
