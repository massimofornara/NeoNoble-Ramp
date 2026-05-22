// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MetaSwapV3Token {
    string public name;
    string public symbol;
    uint8 public immutable decimals;
    uint256 public totalSupply;
    address public owner;
    bool public paused;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Paused(bool paused);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "ONLY_OWNER");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "PAUSED");
        _;
    }

    constructor(
        string memory tokenName,
        string memory tokenSymbol,
        uint8 tokenDecimals,
        uint256 initialSupply,
        address tokenOwner
    ) {
        require(tokenOwner != address(0), "OWNER_ZERO");
        name = tokenName;
        symbol = tokenSymbol;
        decimals = tokenDecimals;
        owner = tokenOwner;
        _mint(tokenOwner, initialSupply);
    }

    function transfer(address to, uint256 value) external whenNotPaused returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external whenNotPaused returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external whenNotPaused returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "ALLOWANCE");
        allowance[from][msg.sender] = allowed - value;
        _transfer(from, to, value);
        return true;
    }

    function mint(address to, uint256 value) external onlyOwner {
        _mint(to, value);
    }

    function burn(uint256 value) external onlyOwner {
        require(balanceOf[msg.sender] >= value, "BALANCE");
        balanceOf[msg.sender] -= value;
        totalSupply -= value;
        emit Transfer(msg.sender, address(0), value);
    }

    function setPaused(bool value) external onlyOwner {
        paused = value;
        emit Paused(value);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "OWNER_ZERO");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function _transfer(address from, address to, uint256 value) internal {
        require(to != address(0), "TO_ZERO");
        require(balanceOf[from] >= value, "BALANCE");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }

    function _mint(address to, uint256 value) internal {
        require(to != address(0), "TO_ZERO");
        totalSupply += value;
        balanceOf[to] += value;
        emit Transfer(address(0), to, value);
    }
}

contract MetaSwapV3TokenFactory {
    address public owner;
    address[] public allTokens;
    mapping(bytes32 => address) public tokenBySalt;

    event TokenDeployed(
        bytes32 indexed salt,
        address indexed token,
        address indexed tokenOwner,
        string name,
        string symbol,
        uint8 decimals,
        uint256 supply
    );
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "ONLY_OWNER");
        _;
    }

    constructor(address initialOwner) {
        require(initialOwner != address(0), "OWNER_ZERO");
        owner = initialOwner;
    }

    function deployToken(
        string memory name,
        string memory symbol,
        uint256 supply,
        uint8 decimals,
        address tokenOwner
    ) external onlyOwner returns (address token) {
        bytes32 salt = keccak256(abi.encode(name, symbol, supply, decimals, tokenOwner, block.chainid));
        require(tokenBySalt[salt] == address(0), "TOKEN_EXISTS");
        token = address(new MetaSwapV3Token{salt: salt}(name, symbol, decimals, supply, tokenOwner));
        tokenBySalt[salt] = token;
        allTokens.push(token);
        emit TokenDeployed(salt, token, tokenOwner, name, symbol, decimals, supply);
    }

    function allTokensLength() external view returns (uint256) {
        return allTokens.length;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "OWNER_ZERO");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
