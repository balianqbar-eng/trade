import Foundation

struct QuoteModel: Codable {
    let ticker: String
    let name: String
    let close: Double
    let open: Double
    let high: Double
    let low: Double
    let change: Double
    let changePct: Double
    let volume: Int
}

struct TechnicalModel: Codable {
    let ticker: String
    let last: Double
    let prev: Double
    let ma5: Double
    let ma20: Double
    let ma60: Double
    let rsi: Double
    let macd: Double
    let signal: Double
    let histogram: Double
}

struct ValuationData {
    let pe: Double?
    let pb: Double?
    let dividendYield: Double?
}

struct InstitutionalData {
    let foreignNet: Double
    let investTrustNet: Double
    let dealerNet: Double
    var total: Double { foreignNet + investTrustNet + dealerNet }
}
