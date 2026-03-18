// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title DealProof
/// @notice Escrow contract that releases payment on verified TEE attestation.
/// Phase 4 — not yet deployed. Interface only.
contract DealProof {
    enum DealState { Pending, Active, Completed, Refunded }

    struct Deal {
        address buyer;
        address seller;
        bytes32 dataHash;
        uint256 amount;
        DealState state;
        uint256 deadline;  // Unix timestamp after which buyer may refund unilaterally
    }

    mapping(bytes32 => Deal) public deals;

    event DealCreated(bytes32 indexed dealId, address buyer, address seller, uint256 amount);
    event DealCompleted(bytes32 indexed dealId, bytes teeAttestation);
    event DealRefunded(bytes32 indexed dealId);

    /// @notice Buyer creates a deal and deposits escrow funds.
    /// @param negotiationWindow Seconds from now during which the TEE may complete
    ///        the deal. The buyer cannot unilaterally refund before this expires.
    function createDeal(
        bytes32 dealId,
        address seller,
        bytes32 dataHash,
        uint256 negotiationWindow
    ) external payable {
        require(msg.value > 0, "Must deposit escrow");
        require(deals[dealId].buyer == address(0), "Deal already exists");
        require(negotiationWindow > 0, "Negotiation window must be positive");

        deals[dealId] = Deal({
            buyer: msg.sender,
            seller: seller,
            dataHash: dataHash,
            amount: msg.value,
            state: DealState.Active,
            deadline: block.timestamp + negotiationWindow
        });

        emit DealCreated(dealId, msg.sender, seller, msg.value);
    }

    /// @notice Complete the deal — verifies TEE attestation and releases payment.
    /// Only the buyer (acting on behalf of the agreed result) may call this.
    /// Phase 4: replace the msg.sender check with on-chain TDX quote verification
    /// (e.g. automata-dcap-attestation) so the TEE itself can trigger completion
    /// without requiring the buyer's signature.
    function completeDeal(bytes32 dealId, bytes memory teeAttestation) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        // Temporary guard: only the buyer can submit the attestation until
        // Phase 4 implements on-chain TDX quote verification.
        require(msg.sender == deal.buyer, "Only buyer can complete deal");
        // TODO Phase 4: verify teeAttestation on-chain (replace msg.sender check above)
        deal.state = DealState.Completed;
        payable(deal.seller).transfer(deal.amount);
        emit DealCompleted(dealId, teeAttestation);
    }

    /// @notice Refund the buyer if negotiation fails or the deadline has passed.
    /// The buyer must wait for the negotiation window to expire before claiming
    /// a unilateral refund — this prevents front-running the TEE result.
    function refund(bytes32 dealId) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        require(msg.sender == deal.buyer, "Only buyer can refund");
        require(block.timestamp >= deal.deadline, "Negotiation window still active");
        deal.state = DealState.Refunded;
        payable(deal.buyer).transfer(deal.amount);
        emit DealRefunded(dealId);
    }
}
