import XCTest
@testable import agentacct

/// The receipt line items are derived state: each test pins one payload shape
/// so a partial or absent value can never render as a measured zero.
final class RecordSummaryPresentationTests: XCTestCase {
    private func inputs(
        checksTotal: Int? = nil, checksPassed: Int? = nil, checksFailed: Int? = nil,
        toolValue: String? = "120", toolQualifier: String? = "tool calls", toolAbsent: String? = nil,
        costUsd: Double? = 3.2, costBasis: String? = "provider_billed",
        costComplete: Bool? = true, costConfidence: String? = "recorded",
        sessionCount: Int? = 2, sessionRoots: Int = 1,
        coverageChecked: Int? = 3, coverageTotal: Int? = 4, coverageInconsistent: Bool = false
    ) -> RecordSummaryPresentation.Inputs {
        .init(checksTotal: checksTotal, checksPassed: checksPassed, checksFailed: checksFailed,
              toolCalls: .init(value: toolValue, qualifier: toolQualifier, absent: toolAbsent),
              costUsd: costUsd, costBasis: costBasis, costComplete: costComplete,
              costConfidence: costConfidence,
              sessionCount: sessionCount, sessionRoots: sessionRoots,
              coverageChecked: coverageChecked, coverageTotal: coverageTotal,
              coverageInconsistent: coverageInconsistent)
    }

    private func item(_ presentation: RecordSummaryPresentation, _ id: String) -> ReceiptSummaryItem? {
        presentation.items.first { $0.id == id }
    }

    func testChecksReportTalliesPartialPayloadsAndNamedAbsence() {
        let failed = RecordSummaryPresentation(inputs: inputs(checksTotal: 16, checksPassed: 14, checksFailed: 2))
        XCTAssertEqual(item(failed, "checks")?.value, "14/16")
        XCTAssertEqual(item(failed, "checks")?.qualifier, "2 failed")

        let clean = RecordSummaryPresentation(inputs: inputs(checksTotal: 16, checksPassed: 16, checksFailed: 0))
        XCTAssertEqual(item(clean, "checks")?.qualifier, "passed")

        // Partial payloads name what is missing instead of implying zero.
        let passedOnly = RecordSummaryPresentation(inputs: inputs(checksPassed: 5))
        XCTAssertEqual(item(passedOnly, "checks")?.value, "5")
        XCTAssertEqual(item(passedOnly, "checks")?.qualifier, "passed · total not reported")

        let totalsOnly = RecordSummaryPresentation(inputs: inputs(checksTotal: 6))
        XCTAssertEqual(item(totalsOnly, "checks")?.value, "6")
        XCTAssertEqual(item(totalsOnly, "checks")?.qualifier, "checks · results not reported")

        let none = RecordSummaryPresentation(inputs: inputs())
        XCTAssertNil(item(none, "checks")?.value)
        XCTAssertEqual(item(none, "checks")?.absent, "no checks recorded")
    }

    func testCostKeepsItsBasisAndNamesMissingPricing() {
        let partial = RecordSummaryPresentation(inputs: inputs(costBasis: "estimated", costComplete: false))
        let cost = item(partial, "cost")
        XCTAssertNotNil(cost?.value)
        XCTAssertEqual(cost?.qualifier?.contains("estimated"), true)
        XCTAssertEqual(cost?.qualifier?.contains("partial"), true)

        let unpriced = RecordSummaryPresentation(inputs: inputs(costUsd: nil))
        XCTAssertNil(item(unpriced, "cost")?.value)
        XCTAssertEqual(item(unpriced, "cost")?.absent, "no priced usage")
    }

    func testCoverageNamesInconsistencyAndNeverFabricates() {
        let inconsistent = RecordSummaryPresentation(inputs: inputs(coverageInconsistent: true))
        XCTAssertEqual(item(inconsistent, "coverage")?.value, "Inconsistent")
        XCTAssertEqual(item(inconsistent, "coverage")?.isWarning, true)

        let reported = RecordSummaryPresentation(inputs: inputs())
        XCTAssertEqual(item(reported, "coverage")?.value, "3/4")
        XCTAssertEqual(item(reported, "coverage")?.qualifier, "of checkable claims")

        let missing = RecordSummaryPresentation(inputs: inputs(coverageChecked: nil, coverageTotal: nil))
        XCTAssertNil(item(missing, "coverage")?.value)
        XCTAssertEqual(item(missing, "coverage")?.absent, "not reported")
    }

    func testSessionsQualifyMultipleRootsAndAbsence() {
        let multiple = RecordSummaryPresentation(inputs: inputs(sessionCount: 4, sessionRoots: 3))
        XCTAssertEqual(item(multiple, "sessions")?.value, "4")
        XCTAssertEqual(item(multiple, "sessions")?.qualifier, "3 roots")

        let single = RecordSummaryPresentation(inputs: inputs(sessionCount: 1, sessionRoots: 1))
        XCTAssertNil(item(single, "sessions")?.qualifier)

        let missing = RecordSummaryPresentation(inputs: inputs(sessionCount: nil))
        XCTAssertEqual(item(missing, "sessions")?.absent, "not recorded")
    }

    func testFixtureReceiptProducesTheFiveOrderedLineItems() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "dashboard", withExtension: "json"))
        let fixture = try DashboardSnapshotFixture.load(from: url)
        let receipt = try XCTUnwrap(fixture.work?.receipt)

        let presentation = RecordSummaryPresentation(receipt: receipt, summary: nil)
        XCTAssertEqual(presentation.items.map(\.id), ["checks", "actions", "cost", "sessions", "coverage"])
        XCTAssertEqual(presentation.items.map(\.label), ["Checks", "Tool calls", "Cost", "Sessions", "Coverage"])
        // Every line item is either a value with its label or a named absence.
        for item in presentation.items {
            XCTAssertTrue(item.value != nil || item.absent != nil, item.id)
        }
    }
}
