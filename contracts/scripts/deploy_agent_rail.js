const { ethers } = require("hardhat");

// Not run as of Phase 3 — AgentDealEscrow has not been deployed to any live
// network. Kept here so a real deployment (Sepolia or otherwise) is a single
// `npx hardhat run scripts/deploy_agent_rail.js --network sepolia` away when
// that's actually decided, mirroring deploy.js for DealProof.sol.
async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying AgentDealEscrow with account:", deployer.address);
  console.log("Account balance:", (await ethers.provider.getBalance(deployer.address)).toString());

  const AgentDealEscrow = await ethers.getContractFactory("AgentDealEscrow");
  const contract = await AgentDealEscrow.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("\nAgentDealEscrow deployed to:", address);
  console.log("\nAdd this to your .env:");
  console.log(`AGENTRAIL_CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
