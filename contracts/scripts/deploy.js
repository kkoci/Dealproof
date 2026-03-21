const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying DealProof with account:", deployer.address);
  console.log("Account balance:", (await ethers.provider.getBalance(deployer.address)).toString());

  const DealProof = await ethers.getContractFactory("DealProof");
  const contract = await DealProof.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("\nDealProof deployed to:", address);
  console.log("\nAdd this to your .env:");
  console.log(`CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
