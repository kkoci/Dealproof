// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentDealEscrow
/// @notice Agent Rail Phase 3 — escrow for B2B agent-to-agent procurement deals.
/// Mirrors DealProof.sol's deposit -> release/refund pattern (Option A: buyer
/// submits the attestation; Option B on-chain DCAP verification is future work,
/// same as DealProof.sol). Adds a dispute state DealProof.sol doesn't need,
/// since procurement deals settle on hardware attestation, not human dispute
/// resolution, except when a party wants to freeze settlement pending review.
///
/// Written and tested against a local Hardhat network only — not deployed to
/// Sepolia or any other live network as of Phase 3. See app/agentrail/escrow.py
/// for the Python wrapper (fully unit-tested with mocked web3.py, same as
/// app/contract/escrow.py for DealProof.sol).
contract AgentDealEscrow {
    enum DealState { Pending, Active, Completed, Refunded, Disputed }

    struct Deal {
        address buyer;
        address supplier;
        uint256 amount;
        DealState state;
        uint256 deadline;  // Unix timestamp after which buyer may refund unilaterally
    }

    address public owner;

    mapping(bytes32 => Deal) public deals;

    /// @notice Stores keccak256(teeAttestation) for each completed deal.
    mapping(bytes32 => bytes32) public attestationHashes;

    event DealCreated(bytes32 indexed dealId, address buyer, address supplier, uint256 amount);
    event DealCompleted(bytes32 indexed dealId, bytes32 indexed attestationHash, bytes teeAttestation);
    event DealRefunded(bytes32 indexed dealId);
    event DealDisputed(bytes32 indexed dealId, address raisedBy);
    event DisputeResolved(bytes32 indexed dealId, bool releasedToSupplier);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /// @notice Buyer creates a deal and deposits escrow funds.
    /// @param dealId     keccak256 of the off-chain deal UUID
    /// @param supplier   Ethereum address that receives payment on completion
    /// @param negotiationWindow Seconds from now during which the TEE may complete
    ///        the deal. The buyer cannot unilaterally refund before this expires.
    function createDeal(
        bytes32 dealId,
        address supplier,
        uint256 negotiationWindow
    ) external payable {
        require(msg.value > 0, "Must deposit escrow");
        require(deals[dealId].buyer == address(0), "Deal already exists");
        require(supplier != address(0), "Invalid supplier address");
        require(negotiationWindow > 0, "Negotiation window must be positive");

        deals[dealId] = Deal({
            buyer: msg.sender,
            supplier: supplier,
            amount: msg.value,
            state: DealState.Active,
            deadline: block.timestamp + negotiationWindow
        });

        emit DealCreated(dealId, msg.sender, supplier, msg.value);
    }

    /// @notice Complete the deal — commits TEE attestation hash and releases payment.
    /// Only the buyer may submit the attestation (same asymmetry as DealProof.sol
    /// Option A — the TEE cannot yet self-submit without on-chain DCAP verification).
    function completeDeal(bytes32 dealId, bytes memory teeAttestation) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        require(msg.sender == deal.buyer, "Only buyer can complete deal");
        require(teeAttestation.length > 0, "Attestation cannot be empty");

        bytes32 attestationHash = keccak256(teeAttestation);
        attestationHashes[dealId] = attestationHash;
        deal.state = DealState.Completed;

        payable(deal.supplier).transfer(deal.amount);

        emit DealCompleted(dealId, attestationHash, teeAttestation);
    }

    /// @notice Refund the buyer if negotiation fails or the deadline has passed.
    function refund(bytes32 dealId) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        require(msg.sender == deal.buyer, "Only buyer can refund");
        require(block.timestamp >= deal.deadline, "Negotiation window still active");

        deal.state = DealState.Refunded;
        payable(deal.buyer).transfer(deal.amount);

        emit DealRefunded(dealId);
    }

    /// @notice Either party freezes settlement pending manual review. Once
    /// disputed, neither completeDeal nor refund can be called until the
    /// owner resolves it — prevents a race between a late attestation and an
    /// expiring deadline when a party contests the outcome.
    function raiseDispute(bytes32 dealId) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        require(msg.sender == deal.buyer || msg.sender == deal.supplier, "Not a party to this deal");

        deal.state = DealState.Disputed;
        emit DealDisputed(dealId, msg.sender);
    }

    /// @notice Owner resolves a dispute by releasing to one side. There is no
    /// automated arbitrator wallet yet (Phase 3 scope, see build_spec_agent_rail.md
    /// Decision 3 — OAuth3/agent-delegation auth is still pending); this is a
    /// manual circuit-breaker, not a trust-minimized resolution mechanism.
    function resolveDispute(bytes32 dealId, bool releaseToSupplier) external onlyOwner {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Disputed, "Deal not disputed");

        deal.state = DealState.Completed;
        if (releaseToSupplier) {
            payable(deal.supplier).transfer(deal.amount);
        } else {
            payable(deal.buyer).transfer(deal.amount);
        }

        emit DisputeResolved(dealId, releaseToSupplier);
    }

    /// @notice Returns the attestation hash committed for a completed deal.
    function getAttestationHash(bytes32 dealId) external view returns (bytes32) {
        return attestationHashes[dealId];
    }
}
