import SwiftUI
#if os(iOS)
import WebKit
#endif

struct NewsView: View {
    let ticker: String
    let name: String

    private var newsURL: URL {
        let query = "\(name) \(ticker)".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ticker
        return URL(string: "https://tw.news.yahoo.com/search?p=\(query)")!
    }

    var body: some View {
        #if os(iOS)
        WebView(url: newsURL)
            .ignoresSafeArea(edges: .bottom)
        #else
        VStack {
            Text("消息面").font(.headline)
            Link("開啟新聞頁面", destination: newsURL)
        }
        #endif
    }
}

#if os(iOS)
struct WebView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
#endif
