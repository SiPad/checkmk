// Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
// This file is part of Checkmk (https://checkmk.com). It is subject to the
// terms and conditions defined in the file COPYING, which is part of this
// source code package.

#ifndef TableStatus_h
#define TableStatus_h

#include <string>

#include "livestatus/Row.h"
#include "livestatus/Table.h"

class ColumnOffsets;
enum class Counter;
class ICore;
class Query;
class User;

class TableStatus : public Table {
public:
    explicit TableStatus(ICore *mc);

    [[nodiscard]] std::string name() const override;
    [[nodiscard]] std::string namePrefix() const override;
    void answerQuery(Query &query, const User &user) override;
    [[nodiscard]] Row getDefault() const override;

private:
    void addCounterColumns(const std::string &name,
                           const std::string &description,
                           const ColumnOffsets &offsets, Counter which);
};

#endif  // TableStatus_h
