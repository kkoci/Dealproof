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
    }

    mapping(bytes32 => Deal) public deals;

    event DealCreated(bytes32 indexed dealId, address buyer, address seller, uint256 amount);
    event DealCompleted(bytes32 indexed dealId, bytes teeAttestation);
    event DealRefunded(bytes32 indexed dealId);

    /// @notice Buyer creates a deal and deposits escrow funds.
    function createDeal(
        bytes32 dealId,
        address seller,
        bytes32 dataHash
    ) external payable {
        require(msg.value > 0, "Must deposit escrow");
        require(deals[dealId].buyer == address(0), "Deal already exists");

        deals[dealId] = Deal({
            buyer: msg.sender,
            seller: seller,
            dataHash: dataHash,
            amount: msg.value,
            state: DealState.Active
        });

        emit DealCreated(dealId, msg.sender, seller, msg.value);
    }

    /// @notice Complete the deal — verifies TEE attestation and releases payment.
    /// Phase 4: attestation verification logic will go here (dstack quote verification).
    function completeDeal(bytes32 dealId, bytes memory teeAttestation) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        // TODO Phase 4: verify teeAttestation on-chain
        deal.state = DealState.Completed;
        payable(deal.seller).transfer(deal.amount);
        emit DealCompleted(dealId, teeAttestation);
    }

    /// @notice Refund the buyer if negotiation fails.
    function refund(bytes32 dealId) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        require(msg.sender == deal.buyer, "Only buyer can refund");
        deal.state = DealState.Refunded;
        payable(deal.buyer).transfer(deal.amount);
        emit DealRefunded(dealId);
    }
}
