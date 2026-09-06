# Z1R (Zelda 1 Randomizer) Complete Memory Reference

This document compiles all known RAM addresses, ROM data locations, and data structures for tracking NES Zelda Randomizer (Z1R) gameplay.

---

## 1. RAM ADDRESSES (NES Internal RAM $0000-$07FF)

### 1.1 Link's Inventory (Items, Swords, Shields, etc.)

| Address | Size | Description | Values |
|---------|------|-------------|--------|
| **$0657** | 1 byte | Current Sword | 00=None, 01=Wooden, 02=White, 03=Magical, 04=Red/Green, 05=Wooden (no melee), 06=White (powerful melee), 07=Magic sword (regular sprite) |
| **$0658** | 1 byte | Bomb Count | Current number of bombs |
| **$0659** | 1 byte | Arrow Type | 00=None, 01=Wooden, 02=Silver, 03=Red, 04=Black |
| **$065A** | 1 byte | Bow in Inventory | 00=False, 01=True |
| **$065B** | 1 byte | Candle Type | 00=None, 01=Blue, 02=Red, 03=Green, 04=Brown, 05=Blue (infinite) |
| **$065C** | 1 byte | Whistle/Recorder | 00=False, 01=True |
| **$065D** | 1 byte | Food/Bait | 00=False, 01=True |
| **$065E** | 1 byte | Potion/Medicine | 00=None/Letter, 01=Blue (Life), 02=Red (2nd Potion) |
| **$065F** | 1 byte | Magical Rod | 00=False, 01=True |
| **$0660** | 1 byte | Raft | 00=False, 01=True |
| **$0661** | 1 byte | Magic Book | 00=False, 01=True |
| **$0662** | 1 byte | Ring | 00=None, 01=Blue, 02=Red (doesn't affect color) |
| **$0663** | 1 byte | Stepladder | 00=False, 01=True |
| **$0664** | 1 byte | Magical Key | 00=False, 01=True |
| **$0665** | 1 byte | Power Bracelet | 00=False, 01=True |
| **$0666** | 1 byte | Letter | 00=False, 01=True, 02=Can buy potions |
| **$0667** | 1 byte | Compass (Levels 1-8) | Bit flags (1 bit per level) |
| **$0668** | 1 byte | Map (Levels 1-8) | Bit flags (1 bit per level) |
| **$0669** | 1 byte | Level 9 Compass | Bit flag |
| **$066A** | 1 byte | Level 9 Map | Bit flag |
| **$066C** | 1 byte | Clock | 00=False, 01=True |
| **$066D** | 1 byte | Rupees (low byte) | Combined with $066E for 16-bit? Actually $066D is single byte |
| **$066E** | 1 byte | Keys | Current key count |
| **$0674** | 1 byte | Boomerang | 00=False, 01=True (overridden by $0675) |
| **$0675** | 1 byte | Magical Boomerang | 00=False, 01=True, 02=Orange, 03=Dark, 04=Mini |
| **$0676** | 1 byte | Magic Shield | 00=False, 01=True |

### 1.2 Heart Containers & Health

| Address | Size | Description | Values |
|---------|------|-------------|--------|
| **$066F** | 1 byte | Heart Containers | High nibble = max containers - 1, Low nibble = hearts filled. Ex: $10 = 2 containers, 0 filled; $22 = 3 containers, 2 filled |
| **$0670** | 1 byte | Partial Heart | 00=Empty, 01-7F=Half, 80-FF=Full |

### 1.3 Triforce Pieces

| Address | Size | Description | Values |
|---------|------|-------------|--------|
| **$0671** | 1 byte | Triforce Pieces | One bit per piece (8 bits = 8 pieces) |

### 1.4 Dungeon Completion Flags

| Address Range | Size | Description | Bit Flags |
|---------------|------|-------------|-----------|
| **$0700-$077F** | 128 bytes | Levels 1-6 Room Status | Bit 0=West open, Bit 1=East open, Bit 2=South open, Bit 3=North open, Bit 4=Item taken, Bit 5=Visited, Bit 6=One enemy killed, Bit 7=All enemies killed (with Bit 6) |
| **$0780-$07FE** | 127 bytes | Levels 7-9 Room Status | Same format as above |

### 1.5 Overworld Cave/Room Completion Flags

| Address Range | Size | Description | Bit Flags |
|---------------|------|-------------|-----------|
| **$067F-$06FE** | 128 bytes | Overworld Screen State | Format: %Ss-I-EEE: S=Secret discovered, s=Pushable rock stairs found, I=Item obtained, E=Enemies killed |

### 1.6 Dungeon Item Taken Flags (Room Status)

The room status bytes at $0700-$07FE contain item collection info:
- **Bit 4 (0x10)**: Room Item Taken
- **Bit 5 (0x20)**: Room Visited

### 1.7 Game State & Location

| Address | Size | Description |
|---------|------|-------------|
| **$0010** | 1 byte | Current Level (0=Overworld, 1-9=Dungeon) |
| **$0012** | 1 byte | Game Mode (00=Title, 01=Select, 02=Transition, 05=Normal, 06=Prep Scroll, 07=Scrolling, 0A=Leave Grotto, 0B=Grotto, 0E=Elimination, 0F=Registration, 10=Stairs In) |
| **$00EB** | 1 byte | Current Room (00-7F) - High nibble=row, Low nibble=col |
| **$00EC** | 1 byte | Next Room |
| **$0526** | 1 byte | Overworld Return Room (FF=None, else room to return to when exiting underworld) |

### 1.8 Screen History (Recent Rooms)

| Address Range | Size | Description |
|---------------|------|-------------|
| **$0620** | 1 byte | Room History Write Index |
| **$0621-$0625** | 5 bytes | Last 5 visited room IDs |

### 1.9 Save Slot Data (SRAM mirrored to RAM)

| Address Range | Slot | Description |
|---------------|------|-------------|
| **$0638-$063F** | 1 | Player Name (8 bytes) |
| **$0640-$0647** | 2 | Player Name (8 bytes) |
| **$0648-$064F** | 3 | Player Name (8 bytes) |
| **$0650-$0651** | 1 | Heart Containers + Fill (File Select display) |
| **$0652-$0653** | 2 | Heart Containers + Fill |
| **$0654-$0655** | 3 | Heart Containers + Fill |
| **$062D** | 1 | Quest Type (00=First, 01=Second) |
| **$062E** | 2 | Quest Type |
| **$062F** | 3 | Quest Type |
| **$0630** | 1 | Death Counter |
| **$0631** | 2 | Death Counter |
| **$0632** | 3 | Death Counter |

---

## 2. SRAM / SAVE DATA ($6000-$7FFF)

### 2.1 Save Slot Structure (Per Slot)

Based on ROM Detectives Wiki and Data Crystal:

**Slot 1 Base: $6000**
**Slot 2 Base: $6028** (offset +$28)
**Slot 3 Base: $6050** (offset +$50)

| Offset | Size | Description |
|--------|------|-------------|
| +$00 | 8 bytes | Player Name |
| +$08 | 1 byte | Sword Type |
| +$09 | 1 byte | Bomb Count |
| +$0A | 1 byte | Arrow Type |
| +$0B | 1 byte | Candle Type |
| +$0C | 1 byte | Bow Flag |
| +$0D | 1 byte | Whistle Flag |
| +$0E | 1 byte | Food Flag |
| +$0F | 1 byte | Potion Type |
| +$10 | 1 byte | Magical Rod |
| +$11 | 1 byte | Raft |
| +$12 | 1 byte | Book |
| +$13 | 1 byte | Ring |
| +$14 | 1 byte | Stepladder |
| +$15 | 1 byte | Magical Key |
| +$16 | 1 byte | Bracelet |
| +$17 | 1 byte | Letter |
| +$18 | 1 byte | Compass (bit flags) |
| +$19 | 1 byte | Map (bit flags) |
| +$1A | 1 byte | Level 9 Compass |
| +$1B | 1 byte | Level 9 Map |
| +$1C | 1 byte | Clock |
| +$1D | 1 byte | Rupees |
| +$1E | 1 byte | Keys |
| +$1F | 1 byte | Heart Containers |
| +$20 | 1 byte | Partial Heart |
| +$21 | 1 byte | Triforce Pieces |
| +$22 | 1 byte | Boomerang |
| +$23 | 1 byte | Magical Boomerang |
| +$24 | 1 byte | Magic Shield |
| +$25 | 1 byte | Max Bombs |

### 2.2 Room Status Save Data

| Address Range | Slot | Description |
|---------------|------|-------------|
| **$6092-$6121** | 1 | Overworld Enemy Kill Counts (128 bytes) |
| **$6122-$6221** | 1 | Underworld Room Status (256 bytes) |
| **$6292-$6321** | 2 | Overworld Enemy Kill Counts |
| **$6322-$6421** | 2 | Underworld Room Status |
| **$6492-$6521** | 3 | Overworld Enemy Kill Counts |
| **$6522-$6621** | 3 | Underworld Room Status |

### 2.3 Link's Tunic Colors (Per Slot)

| Address | Slot | Description |
|---------|------|-------------|
| **$6804** | 1 | Tunic Color ($29=Green, $32=Blue, $16=Red) |
| **$6805** | 1 | Skin Color |
| **$6806** | 1 | Belt Color |
| **$6808** | 2 | Tunic Color |
| **$6809** | 2 | Skin Color |
| **$680A** | 2 | Belt Color |
| **$680C** | 3 | Tunic Color |
| **$680D** | 3 | Skin Color |
| **$680E** | 3 | Belt Color |

---

## 3. ROM ADDRESSES (NES PRG-ROM)

### 3.1 Item & Cave Data Tables

| Address | Size | Description |
|---------|------|-------------|
| **$18600-$18602** | 3 bytes | Wooden Sword Cave items (final item has bit 6 set) |
| **$18603-$18605** | 3 bytes | Free Heart/Letter Cave items (final item has bit 6 set) |
| **$18606-$18608** | 3 bytes | White Sword Cave items (first AND final have bit 6 set) |
| **$18609-$1860B** | 3 bytes | Magical Sword Cave items (first AND final have bit 6 set) |
| **$18618-$1861A** | 3 bytes | Letter Cave items (final item has bit 6 set) |
| **$18622-$18624** | 3 bytes | Gambling Cave items (final item has bit 6 set) |
| **$1861E-$18620** | 3 bytes | Potion Shop items (final has bits 6&7 set) |
| **$18627-$18629** | 3 bytes | Shop A items (final has bits 6&7 set) |
| **$1862A-$1862C** | 3 bytes | Shop B items |
| **$18648+** | - | Item Prices (3 bytes per cave) |
| **$06E6F** | - | Cave Dweller Type (58=Old Man, 59=Old Woman, 5A=Merchant, 5B=Moblin) |

### 3.2 Overworld Special Item Locations (Shuffled by Z1R)

| Address | Description |
|---------|-------------|
| **$10CF5** | Armos Statue Item |
| **$1788A** | Coast/Stepladder Heart Container Item |
| **$18607** | White Sword Cave Item (part of $18606-$18608) |

### 3.3 Dungeon Data Pointers

| Address | Description |
|---------|-------------|
| **$18000** | Overworld PPU Spriteblock Pointer |
| **$18002** | Levels 1-6 Data Pointer |
| **$1800E** | Levels 7-9 Data Pointer |
| **$18014** | Overworld Level Data Blocks Pointer |
| **$18016** | Levels 1-6 Level Data Pointer |
| **$18022** | Levels 7-9 Level Data Pointer |

### 3.4 Dungeon Layout Data Locations

| Location | Address Range | Size | Quest |
|----------|---------------|------|-------|
| Overworld | $18400-$186FF | $300 | - |
| Levels 1-6 (1st Quest) | $18700-$189FF | $300 | 1st |
| Levels 7-9 (1st Quest) | $18A00-$18CFF | $300 | 1st |
| Levels 1-6 (2nd Quest) | $18D00-$18FFF | $300 | 2nd |
| Levels 7-9 (2nd Quest) | $19000-$192FF | $300 | 2nd |

### 3.5 Requirements & Flags

| Address | Description |
|---------|-------------|
| **$5F17** | Triforce Requirement (pieces needed) |
| **$48FD** | White Sword Heart Requirement (value/16 + 1) |
| **$4906** | Magical Sword Heart Requirement (value/16 + 1) |
| **$4890** | Door Repair Charge |

### 3.6 Overworld Map Data

| Address | Description |
|---------|-------------|
| **$18580-$185FF** | Overworld Screen Arrangement (8x16 screens, bit 7=monster groups) |
| **$18600-$1867F** | Store Prices, Items, Graphics |

### 3.7 Item ID Reference (ROM Item List)

| ID | Item |
|----|------|
| 01 | Sword |
| 02 | White Sword |
| 03 | Magic Sword |
| 04 | Bait |
| 05 | Recorder |
| 06 | Blue Candle |
| 07 | Red Candle |
| 08 | Arrow |
| 09 | Silver Arrow |
| 0A | Bow |
| 0B | Magic Key |
| 0C | Raft |
| 0D | Stepladder |
| 0E | Moblin (Error) |
| 0F | 5 Rupees |
| 10 | Rod |
| 11 | Book |
| 12 | Blue Ring |
| 13 | Red Ring |
| 14 | Bracelet |
| 15 | Letter |
| 16 | Compass |
| 17 | Map |
| 18 | Rupee |
| 19 | Key |
| 1A | Heart Container |
| 1B | Triforce |
| 1C | Magic Shield |
| 1D | Boomerang |
| 1E | Magic Boomerang |
| 1F | Blue Medicine |
| 20 | Red Medicine |
| 21 | Clock |
| 22 | Heart |
| 23 | Fairy (Flying) |
| 24 | Fairy (Stationary) |

---

## 4. Z1R-SPECIFIC INFORMATION

### 4.1 Dungeon Quest Types & Item Distribution

The randomizer uses these Dungeon Quest settings which determine item slot layout:

| Level | 1st Quest | 2nd Quest | Shapes |
|-------|-----------|-----------|--------|
| 1 | Floor + Stair | Floor | 1st Quest logic |
| 2 | Floor | Stair | 1st Quest logic |
| 3 | Stair | Floor | 1st Quest logic |
| 4 | Stair | Stair ×2 | 1st Quest logic |
| 5 | Stair | Stair | 1st Quest logic |
| 6 | Stair | Stair | 1st Quest logic |
| 7 | Stair | Stair | 1st Quest logic |
| 8 | Stair ×2 | Stair ×2 | 1st Quest logic |
| 9 | Stair ×2 | Stair ×2 | 1st Quest logic |

**Key Points:**
- Both quests hold 12 dungeon items total
- Every level except 9 has a Heart Container
- **Mixed Quest**: Levels 1-6 from one quest, 7-9 from the other
- **Shapes**: Procedurally generated, follows 1st Quest item logic

### 4.2 Named Overworld Locations (Shuffled Independently)

1. **White Sword Cave** - Gated by 4-6 Heart Containers (depends on shop flags)
2. **Armos** - Item under Armos statue ($10CF5 in ROM)
3. **Coast** - Ladder-only coastal spot ($1788A in ROM)

### 4.3 Triforce Distribution

Per Dungeon Quest setting, Triforce pieces are placed in specific dungeons. The tracker models this as one bit per piece at $0671.

### 4.4 Dungeon Item Drop Locations

Item drops occur in specific rooms per dungeon. See: https://docs.google.com/spreadsheets/d/1q_maRTEz9abZJDAhTJgCchd7GzeV0r43QBQLAS5QT2c/edit#gid=0

### 4.5 Hint System

Z1R hints pair a **subject** (dungeon boss phrase or item) with an **overworld region**:

| Code | Region |
|------|--------|
| DM | Death Mountain |
| LK | By a Lake |
| GR | At the Grave |
| CO | The Coast |
| DW | The Dead Woods |
| FO | The Forest |
| RV | The River |
| LH | The Lost Hills |
| CS | Close to Start |
| DE | The Desert |

---

## 5. RANDOMIZER SEED DATA STRUCTURE

The Z1R randomizer (fcoughlin's version) generates a seed that determines:

1. **Dungeon Quest** - Layout type for each dungeon
2. **Item Shuffle** - Which item pool is used
3. **Dungeon Drops** - Whether Triforce/hearts/keys/compass/map are shuffled
4. **Minor Drops** - Whether bomb/rupee/key drops can become major items
5. **Important Items in Level 9** - Ladder, Raft, Bracelet, Recorder, Bow may be in Level 9
6. **Quest Split** - For Mixed/Random: which quest for L1-6 vs L7-9
7. **Overworld Shuffle** - Cave/dungeon entrance locations
8. **Shop Shuffle** - Item prices and stock
9. **Enemy/Monster Shuffle** - Enemy placement

The seed is a 64-bit integer. The flag string encodes all settings.

**The randomizer modifies the ROM directly** - it doesn't store seed data in RAM during gameplay. All randomization is baked into the ROM at generation time. The only way to know the seed/flags during play is:
- Read the spoiler log (external)
- Track manually via tracker
- Parse the ROM's modified data tables

### 4.6 How to Detect Z1R vs Vanilla in RAM

Since Z1R modifies the ROM, not RAM:
- Check ROM at $18606 (White Sword Cave) - if not the vanilla item, it's randomized
- Check ROM at $10CF5 (Armos) and $1788A (Coast)
- Check dungeon data pointers at $18002, $1800E for non-vanilla values
- Check room status flags at $0700+ for unexpected item locations

---

## 6. TRACKING SPECIFIC LOCATIONS

### 6.1 Dungeon Floor Items (Visible in Room)

Track via room status at $0700+$room_offset:
- **Bit 4 (0x10)** = Item taken from this room
- Room offset corresponds to dungeon map position

### 6.2 Dungeon Stair Items (Basement/Staircase)

Same tracking via room status. Stair items are in specific rooms per dungeon quest type.

### 6.3 Overworld Heart Container Caves

| Cave | ROM Address | RAM Tracking |
|------|-------------|--------------|
| White Sword Cave | $18606-$18608 | Overworld screen state at $067F+ (item obtained bit) |
| Armos Statue | $10CF5 | Overworld screen state |
| Coast (Stepladder) | $1788A | Overworld screen state |
| SE Sea (Bomb) | - | Overworld screen state |
| N of Level 2 (Bomb) | - | Overworld screen state |
| S of Level 1 (Candle) | - | Overworld screen state |
| NE Sea (Raft) | - | Overworld screen state |
| E Sea (Stepladder) | - | Overworld screen state |

### 6.4 Item-to-Location Mapping

To track "which specific item came from which location":

1. **Dungeon Floor Items**: Room ID + Level → Item (via spoiler log or discovery)
2. **Dungeon Stair Items**: Staircase Room ID + Level → Item
3. **Overworld Caves**: Screen ID → Item (3 special caves + 5 heart caves)
4. **Shops**: Shop ID → Item/Price (ROM at $1861E+)
5. **Drops**: Enemy drop tables (minor drops flag)

---

## 7. LUA SCRIPT TEMPLATE FOR TRACKING

```lua
-- Z1R Memory Watch Script for BizHawk/FCEUX
-- Place in Lua console or script file

local z1r = {}

z1r.addr = {
    -- Inventory
    sword       = 0x0657,
    bombs       = 0x0658,
    arrow       = 0x0659,
    bow         = 0x065A,
    candle      = 0x065B,
    whistle     = 0x065C,
    bait        = 0x065D,
    potion      = 0x065E,
    rod         = 0x065F,
    raft        = 0x0660,
    book        = 0x0661,
    ring        = 0x0662,
    ladder      = 0x0663,
    magic_key   = 0x0664,
    bracelet    = 0x0665,
    letter      = 0x0666,
    compass     = 0x0667,
    map         = 0x0668,
    compass_l9  = 0x0669,
    map_l9      = 0x066A,
    clock       = 0x066C,
    rupees      = 0x066D,
    keys        = 0x066E,
    
    -- Health
    heart_containers = 0x066F,
    partial_heart    = 0x0670,
    
    -- Triforce
    triforce_pieces  = 0x0671,
    
    -- Boomerang/Shield
    boomerang        = 0x0674,
    magic_boomerang  = 0x0675,
    magic_shield     = 0x0676,
    
    -- Dungeon Room Status
    dungeon_rooms_l1_6 = 0x0700,  -- 128 bytes
    dungeon_rooms_l7_9 = 0x0780,  -- 127 bytes
    
    -- Overworld Screen State
    overworld_screens  = 0x067F,  -- 128 bytes
    
    -- Location
    current_level = 0x0010,
    current_room  = 0x00EB,
    
    -- Save Slot
    save_slot = 0x0016,
}

function z1r.read_inventory()
    local inv = {}
    inv.sword = memory.readbyte(z1r.addr.sword)
    inv.bombs = memory.readbyte(z1r.addr.bombs)
    inv.arrow = memory.readbyte(z1r.addr.arrow)
    inv.bow = memory.readbyte(z1r.addr.bow)
    inv.candle = memory.readbyte(z1r.addr.candle)
    inv.whistle = memory.readbyte(z1r.addr.whistle)
    inv.bait = memory.readbyte(z1r.addr.bait)
    inv.potion = memory.readbyte(z1r.addr.potion)
    inv.rod = memory.readbyte(z1r.addr.rod)
    inv.raft = memory.readbyte(z1r.addr.raft)
    inv.book = memory.readbyte(z1r.addr.book)
    inv.ring = memory.readbyte(z1r.addr.ring)
    inv.ladder = memory.readbyte(z1r.addr.ladder)
    inv.magic_key = memory.readbyte(z1r.addr.magic_key)
    inv.bracelet = memory.readbyte(z1r.addr.bracelet)
    inv.letter = memory.readbyte(z1r.addr.letter)
    inv.compass = memory.readbyte(z1r.addr.compass)
    inv.map = memory.readbyte(z1r.addr.map)
    inv.clock = memory.readbyte(z1r.addr.clock)
    inv.rupees = memory.readbyte(z1r.addr.rupees)
    inv.keys = memory.readbyte(z1r.addr.keys)
    inv.boomerang = memory.readbyte(z1r.addr.boomerang)
    inv.magic_boomerang = memory.readbyte(z1r.addr.magic_boomerang)
    inv.magic_shield = memory.readbyte(z1r.addr.magic_shield)
    return inv
end

function z1r.read_hearts()
    local hc = memory.readbyte(z1r.addr.heart_containers)
    local max = bit.rshift(hc, 4) + 1
    local filled = bit.band(hc, 0x0F)
    local partial = memory.readbyte(z1r.addr.partial_heart)
    local half = partial >= 0x80 and 1 or (partial > 0 and 0.5 or 0)
    return {max=max, filled=filled, partial=half}
end

function z1r.read_triforce()
    local tf = memory.readbyte(z1r.addr.triforce_pieces)
    local count = 0
    for i=0,7 do
        if bit.band(tf, bit.lshift(1,i)) ~= 0 then count = count + 1 end
    end
    return count
end

function z1r.read_dungeon_cleared(level)
    -- Check if Triforce room (0x30 status) has been visited
    -- Triforce room typically at specific room per level
    local base = (level <= 6) and z1r.addr.dungeon_rooms_l1_6 or z1r.addr.dungeon_rooms_l7_9
    local triforce_rooms = {[1]=0x0C, [2]=0x18, [3]=0x24, [4]=0x30, [5]=0x3C, [6]=0x48, [7]=0x54, [8]=0x60, [9]=0x6C}
    local room = triforce_rooms[level]
    if room then
        local status = memory.readbyte(base + room)
        return bit.band(status, 0x20) ~= 0  -- Visited flag
    end
    return false
end

function z1r.read_overworld_cave_cleared(screen_id)
    -- screen_id 0-127 for overworld screens
    local status = memory.readbyte(z1r.addr.overworld_screens + screen_id)
    return bit.band(status, 0x08) ~= 0  -- Item obtained bit
end

-- Main loop
while true do
    local inv = z1r.read_inventory()
    local hearts = z1r.read_hearts()
    local tf = z1r.read_triforce()
    local level = memory.readbyte(z1r.addr.current_level)
    local room = memory.readbyte(z1r.addr.current_room)
    
    gui.text(10, 10, string.format("Level: %d Room: %02X", level, room))
    gui.text(10, 25, string.format("Hearts: %d/%d (%.1f)", hearts.filled, hearts.max, hearts.filled + hearts.partial))
    gui.text(10, 40, string.format("Triforce: %d/8", tf))
    gui.text(10, 55, string.format("Sword: %d Bombs: %d Keys: %d", inv.sword, inv.bombs, inv.keys))
    gui.text(10, 70, string.format("Items: %s%s%s%s%s%s%s%s%s%s%s%s%s",
        inv.arrow>0 and "Arrow " or "",
        inv.bow>0 and "Bow " or "",
        inv.candle>0 and "Candle " or "",
        inv.whistle>0 and "Whistle " or "",
        inv.rod>0 and "Rod " or "",
        inv.raft>0 and "Raft " or "",
        inv.book>0 and "Book " or "",
        inv.ladder>0 and "Ladder " or "",
        inv.magic_key>0 and "MKey " or "",
        inv.bracelet>0 and "Bracelet " or "",
        inv.letter>0 and "Letter " or "",
        inv.ring>0 and "Ring " or "",
        inv.potion>0 and "Potion " or ""
    ))
    emu.frameadvance()
end
```

---

## 8. KEY RESOURCES & REFERENCES

### Official Sources
- **Z1R Wiki**: https://z1r.wiki/wiki/Zelda_1_Randomizer_Wiki
- **Data Crystal RAM Map**: https://datacrystal.tcrf.net/wiki/The_Legend_of_Zelda/RAM_map
- **ROM Detectives RAM**: http://romdetectives.com/Wiki/index.php?title=The_Legend_of_Zelda_(NES)_-_RAM
- **ROM Detectives ROM**: http://romdetectives.com/Wiki/index.php?title=The_Legend_of_Zelda_(NES)_-_ROM

### Tracker Source Code (Memory Address References)
- **Z1R_Tracker (bryhalterman)**: https://github.com/bryhalterman/Z1R_Tracker
- **ZTracker (brianmcn/Stevie-O)**: https://github.com/brianmcn/Zelda1RandoTools
- **Open Source Randomizer (tetraly)**: https://github.com/tetraly/zelda-randomizer

### Dungeon Drop Locations
- **Google Sheets**: https://docs.google.com/spreadsheets/d/1q_maRTEz9abZJDAhTJgCchd7GzeV0r43QBQLAS5QT2c/edit#gid=0

### Emulator Tools
- **BizHawk**: https://tasvideos.org/BizHawk (Lua scripting, memory domains)
- **FCEUX**: https://fceux.com (Memory Watch, Lua, Hex Editor)
- **Mesen**: https://www.mesen.ca (Debugger, Memory Tools)

---

## 9. SUMMARY: ADDRESSES FOR YOUR TRACKER

### Minimum Required for Basic Tracking:
| Purpose | Address(es) |
|---------|-------------|
| Inventory Items | $0657-$0666, $0674-$0676 |
| Heart Containers | $066F, $0670 |
| Triforce Pieces | $0671 |
| Dungeon Completion | $0700-$07FE (check Triforce room visited bit 0x20) |
| Overworld Caves | $067F-$06FE (check item obtained bit 0x08) |
| Current Level/Room | $0010, $00EB |
| Keys/Rupees | $066E, $066D |

### For "Which Item from Which Location":
1. **Read ROM at generation time** (or spoiler log) for item placement tables
2. **Track in RAM** when item collected:
   - Dungeon: Room status bit 0x10 at $0700+room
   - Overworld: Screen status bit 0x08 at $067F+screen
3. **Map room/screen to location name** using dungeon maps and overworld map

---

*Compiled from Data Crystal (TCRF), ROM Detectives Wiki, Z1R Wiki, Z1R Tracker source code, and tetraly's open-source randomizer. Addresses are for USA Rev 1 (most common).*
