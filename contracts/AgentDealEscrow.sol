// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentDealEscrow
/// @notice STUB — Agent Rail Phase 1. Not deployed, not compiled into the build,
/// not wired to any negotiation flow. Holds the intended shape only, per
/// build_spec_agent_rail.md ("Don't touch the escrow contract yet — just stub it").
///
/// Full implementation (deposit -> negotiate -> release/refund/dispute) is
/// Phase 3 scope. DealProof.sol is the reference implementation for the
/// attestation-gated deposit/release/refund pattern this contract will follow.
contract AgentDealEscrow {
    enum DealState { Pending, Active, Completed, Refunded, Disputed }

    struct Deal {
        address buyer;
        address supplier;
        uint256 amount;
        DealState state;
    }

    mapping(bytes32 => Deal) public deals;

    event DealCreated(bytes32 indexed dealId, address buyer, address supplier, uint256 amount);

    // TODO (Phase 3): deposit(), release(bytes teeAttestation), refund(), dispute()
    // — see DealProof.sol's createDeal/completeDeal/refund for the pattern.
}
