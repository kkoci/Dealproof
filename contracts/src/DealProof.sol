// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title DealProof
/// @notice Escrow contract that releases payment on verified TEE attestation.
/// Phase 4 — Option A: buyer submits attestation, hash committed on-chain.
/// Option B (future): replace msg.sender guard with automata-dcap-attestation
/// so the Phala CVM can autonomously trigger completeDeal via a TEE wallet.
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

    /// @notice Stores keccak256(teeAttestation) for each completed deal.
    /// Allows anyone to verify on-chain that a specific attestation was committed.
    mapping(bytes32 => bytes32) public attestationHashes;

    event DealCreated(bytes32 indexed dealId, address buyer, address seller, uint256 amount);
    event DealCompleted(bytes32 indexed dealId, bytes32 indexed attestationHash, bytes teeAttestation);
    event DealRefunded(bytes32 indexed dealId);

    /// @notice Buyer creates a deal and deposits escrow funds.
    /// @param dealId     keccak256 of the off-chain deal UUID — links on-chain state to the API record
    /// @param seller     Ethereum address that receives payment on completion
    /// @param dataHash   SHA-256 hash of the dataset being sold (32 bytes)
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
        require(seller != address(0), "Invalid seller address");
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

    /// @notice Complete the deal — commits TEE attestation hash and releases payment.
    /// @param dealId         The deal to complete (must be Active)
    /// @param teeAttestation Raw attestation bytes from the TEE (sim_quote or real TDX quote).
    ///                       keccak256 of this is stored on-chain as attestationHashes[dealId].
    ///
    /// Option A (current): only the buyer may submit the attestation. This works
    /// for simulation mode where the TEE cannot self-submit.
    ///
    /// Option B (future): replace the msg.sender check with a call to
    /// automata-dcap-attestation to verify the TDX quote on-chain, allowing the
    /// Phala CVM TEE wallet to call completeDeal autonomously without buyer involvement.
    function completeDeal(bytes32 dealId, bytes memory teeAttestation) external {
        Deal storage deal = deals[dealId];
        require(deal.state == DealState.Active, "Deal not active");
        require(msg.sender == deal.buyer, "Only buyer can complete deal");
        require(teeAttestation.length > 0, "Attestation cannot be empty");

        bytes32 attestationHash = keccak256(teeAttestation);
        attestationHashes[dealId] = attestationHash;
        deal.state = DealState.Completed;

        payable(deal.seller).transfer(deal.amount);

        emit DealCompleted(dealId, attestationHash, teeAttestation);
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

    /// @notice Returns the attestation hash committed for a completed deal.
    /// Returns bytes32(0) if the deal has not been completed.
    function getAttestationHash(bytes32 dealId) external view returns (bytes32) {
        return attestationHashes[dealId];
    }
}
