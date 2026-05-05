import Foundation

@MainActor
class NetworkService: ObservableObject {
    @Published var quote: QuoteModel?
    @Published var technical: TechnicalModel?
    @Published var valuation: ValuationData?
    @Published var institutional: InstitutionalData?
    @Published var isLoading = false
    @Published var error: String?

    private let serverBase = "http://localhost:8000"
    private let twseBase = "https://openapi.twse.com.tw/v1"

    func fetchAll(ticker: String) async {
        isLoading = true
        error = nil
        quote = nil
        technical = nil
        valuation = nil
        institutional = nil

        async let q = fetchQuote(ticker: ticker)
        async let t = fetchTechnical(ticker: ticker)
        async let v = fetchValuation(ticker: ticker)
        async let i = fetchInstitutional(ticker: ticker)

        (quote, technical, valuation, institutional) = await (q, t, v, i)

        if quote == nil {
            error = "查無此股票，或伺服器未啟動（\(serverBase)）"
        }
        isLoading = false
    }

    private func fetchQuote(ticker: String) async -> QuoteModel? {
        guard let url = URL(string: "\(serverBase)/quote/\(ticker)") else { return nil }
        guard let (data, _) = try? await URLSession.shared.data(from: url) else { return nil }
        return try? JSONDecoder().decode(QuoteModel.self, from: data)
    }

    private func fetchTechnical(ticker: String) async -> TechnicalModel? {
        guard let url = URL(string: "\(serverBase)/technical/\(ticker)") else { return nil }
        guard let (data, _) = try? await URLSession.shared.data(from: url) else { return nil }
        return try? JSONDecoder().decode(TechnicalModel.self, from: data)
    }

    private func fetchValuation(ticker: String) async -> ValuationData? {
        guard let url = URL(string: "\(twseBase)/exchangeReport/BWIBBU_d") else { return nil }
        guard let (data, _) = try? await URLSession.shared.data(from: url) else { return nil }
        guard let rows = try? JSONDecoder().decode([[String: String]].self, from: data),
              let row = rows.first(where: { $0["Code"] == ticker }) else { return nil }
        func toDouble(_ key: String) -> Double? {
            Double(row[key]?.replacingOccurrences(of: ",", with: "") ?? "")
        }
        return ValuationData(pe: toDouble("PEratio"), pb: toDouble("PBratio"), dividendYield: toDouble("DividendYield"))
    }

    private func fetchInstitutional(ticker: String) async -> InstitutionalData? {
        guard let url = URL(string: "\(twseBase)/fund/T86") else { return nil }
        guard let (data, _) = try? await URLSession.shared.data(from: url) else { return nil }
        guard let rows = try? JSONDecoder().decode([[String: String]].self, from: data),
              let row = rows.first(where: { $0["Code"] == ticker }) else { return nil }
        func parse(_ key: String) -> Double {
            Double(row[key]?.replacingOccurrences(of: ",", with: "") ?? "0") ?? 0
        }
        return InstitutionalData(
            foreignNet: parse("外陸資買賣超股數(千股)"),
            investTrustNet: parse("投信買賣超股數(千股)"),
            dealerNet: parse("自營商買賣超股數(千股)")
        )
    }
}
